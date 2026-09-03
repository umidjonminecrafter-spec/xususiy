from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization, Branch
from academics.models import Course, Student, Group

User = get_user_model()


class AcademicsAPITests(APITestCase):
    def setUp(self):
        # Create two distinct organizations to test multi-tenancy
        self.org1 = Organization.objects.create(name="Tenant 1")
        self.org2 = Organization.objects.create(name="Tenant 2")

        # Create active subscription for Org 1 and Org 2
        from organizations.models import Subscription, Tariff
        import datetime
        from decimal import Decimal
        today = datetime.date.today()
        default_tariff = Tariff.objects.create(name="Premium", price=Decimal("100.00"), student_limit=0)
        Subscription.objects.create(
            organization=self.org1,
            tariff=default_tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )
        Subscription.objects.create(
            organization=self.org2,
            tariff=default_tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )

        # User for tenant 1
        self.user1 = User.objects.create_user(
            username="teacher1",
            password="password123",
            role="admin",
            organization=self.org1
        )

        # User without organization
        self.user_no_org = User.objects.create_user(
            username="noorguser",
            password="password123",
            role="admin",
            organization=None
        )

        # Course and Student for tenant 1
        self.course1 = Course.objects.create(
            organization=self.org1,
            name="English Advanced",
            price=150.00,
            duration_weeks=12
        )
        self.student1 = Student.objects.create(
            organization=self.org1,
            first_name="Alice",
            last_name="Green",
            phone="+998909998877",
            balance=0.00
        )

        # Student for tenant 2
        self.student2 = Student.objects.create(
            organization=self.org2,
            first_name="Bob",
            last_name="Brown",
            phone="+998906665544",
            balance=0.00
        )

    def test_student_list_tenant_isolation(self):
        """
        Ensure student lists are isolated to the active tenant/organization.
        """
        # Try retrieving students with a user that has no organization, and no org_id query param
        self.client.force_authenticate(user=self.user_no_org)
        url = reverse('student-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

        # Authenticate as user of Org 1, request without org_id -> falls back to user org (Org 1) -> returns Alice
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['first_name'], "Alice")

        # Authenticate as user of Org 1, and explicitly request Org 2.
        # Since self.user1 is NOT a superuser, the override is ignored, and it falls back to Org 1 -> returns Alice (NOT Bob)
        response = self.client.get(f"{url}?org_id={self.org2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['first_name'], "Alice")

        # Create a superuser to verify they CAN override the active organization
        superuser = User.objects.create_superuser(
            username="superuser",
            password="superpassword",
            email="super@admin.com"
        )
        self.client.force_authenticate(user=superuser)

        # Superuser explicitly requests Org 2 -> returns Bob
        response = self.client.get(f"{url}?org_id={self.org2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['first_name'], "Bob")

        # Superuser requests specifying Org 1 explicitly via header -> returns Alice
        response = self.client.get(url, HTTP_X_ORG_ID=str(self.org1.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['first_name'], "Alice")

    def test_add_payment_updates_balance(self):
        """
        Ensure the add-payment student action updates the student's balance.
        """
        self.client.force_authenticate(user=self.user1)
        url = reverse('student-add-payment', kwargs={'pk': self.student1.id})

        data = {
            "amount": 250.00,
            "payment_method": "card"
        }

        response = self.client.post(f"{url}?org_id={self.org1.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(response.data['balance']), 250.00)

        # Verify student balance updated in DB
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.balance, 250.00)

        # Verify students/{id}/ detail endpoint returns updated balance
        detail_url = reverse('student-detail', kwargs={'pk': self.student1.id})
        res_detail = self.client.get(f"{detail_url}?org_id={self.org1.id}")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(float(res_detail.data['balance']), 250.00)

        # Verify student-balances/?student={id} returns updated balance
        bal_url = reverse('student-balance-list')
        res_bal = self.client.get(f"{bal_url}?org_id={self.org1.id}&student={self.student1.id}")
        self.assertEqual(res_bal.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_bal.data), 1)
        self.assertEqual(res_bal.data[0]['student'], self.student1.id)
        self.assertEqual(float(res_bal.data[0]['balance']), 250.00)

        # Verify student-transactions/?student={id} returns payment
        tx_url = reverse('student-transactions')
        res_tx = self.client.get(f"{tx_url}?org_id={self.org1.id}&student={self.student1.id}")
        self.assertEqual(res_tx.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_tx.data), 1)
        self.assertEqual(float(res_tx.data[0]['amount']), 250.00)

    def test_delete_student_creates_archive(self):
        """
        Ensure deleting a student creates an archive entry with the provided reason and comment.
        """
        from academics.models import StudentArchive
        self.client.force_authenticate(user=self.user1)
        url = reverse('student-detail', kwargs={'pk': self.student1.id})

        # Call DELETE with reason and comment parameters
        response = self.client.delete(f"{url}?org_id={self.org1.id}&reason=To'lov&comment=Qarzdorlik sababli")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify student is deleted
        self.assertFalse(Student.objects.filter(id=self.student1.id).exists())

        # Verify archive entry exists with correct details
        archive = StudentArchive.objects.get(phone=self.student1.phone)
        self.assertEqual(archive.reason, "To'lov")
        self.assertEqual(archive.comment, "Qarzdorlik sababli")
        self.assertEqual(archive.organization, self.org1)

    def test_archive_student_deactivates_user_and_restores(self):
        """
        Verify that archiving a student deletes the corresponding User object,
        freeing the phone number, and restoring recreates the User object.
        """
        from accounts.models import User
        from academics.models import StudentArchive

        # Create a user object for student1
        User.objects.create_user(
            username=f"{self.student1.phone}_{self.org1.id}",
            password="studentpassword",
            phone=self.student1.phone,
            role="student",
            organization=self.org1
        )

        self.client.force_authenticate(user=self.user1)
        url = reverse('student-detail', kwargs={'pk': self.student1.id})

        # Archive student1
        response = self.client.delete(f"{url}?org_id={self.org1.id}&reason=TestReason&comment=TestComment")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 1. Verify student User is deleted
        self.assertFalse(User.objects.filter(username=f"{self.student1.phone}_{self.org1.id}", role="student").exists())

        # 2. Verify we can create a new student with that phone number (since it's freed)
        student_create_url = reverse('student-list')
        data = {
            "first_name": "NewAlice",
            "last_name": "NewGreen",
            "phone": self.student1.phone,
            "password": "newpassword123",
            "balance": 0.00
        }
        create_response = self.client.post(f"{student_create_url}?org_id={self.org1.id}", data=data)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        # 3. Verify we can restore the archived student (should fail if username conflict, but let's delete the newly created user first to test successful restore)
        # Delete new student and their user directly from DB to avoid a second archive entry
        new_student_id = create_response.data['id']
        Student.objects.filter(id=new_student_id).delete()
        User.objects.filter(username=f"{self.student1.phone}_{self.org1.id}").delete()

        # Now restore the archived student
        archive_entry = StudentArchive.objects.get(phone=self.student1.phone)
        restore_url = reverse('student-archive-restore', kwargs={'pk': archive_entry.id})
        restore_response = self.client.post(f"{restore_url}?org_id={self.org1.id}")
        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)

        # Verify User is recreated
        self.assertTrue(User.objects.filter(username=f"{self.student1.phone}_{self.org1.id}", role="student").exists())

    def test_attendance_billing_logic(self):
        """
        Verify that marking a student as present/late deducts money from their balance,
        creates a Transaction in the Cashbox, and changing status or deleting refunds it.
        """
        import datetime
        from decimal import Decimal
        from academics.models import StudentGroup, Attendance, GroupLesson
        from finance.models import Cashbox, Transaction

        # 1. Update course price to a larger amount
        self.course1.price = Decimal("120000.00")
        self.course1.save()

        # 2. Create Group
        group = Group.objects.create(
            organization=self.org1,
            course=self.course1,
            name="Group 1",
            status="active",
            days=["mon", "wed", "fri"]
        )

        # 3. Link Student to Group
        StudentGroup.objects.create(
            organization=self.org1,
            student=self.student1,
            group=group,
            price=Decimal("120000.00")
        )

        # 4. Generate 12 GroupLessons in June 2026
        lessons = []
        for i in range(1, 13):
            lessons.append(
                GroupLesson(
                    organization=self.org1,
                    group=group,
                    date=datetime.date(2026, 6, i)
                )
            )
        GroupLesson.objects.bulk_create(lessons)

        # 5. Verify initial balance
        self.assertEqual(self.student1.balance, Decimal("0.00"))

        # 6. Create attendance on 2026-06-01 as 'present'
        att = Attendance.objects.create(
            organization=self.org1,
            student=self.student1,
            group=group,
            date=datetime.date(2026, 6, 1),
            status="present"
        )

        # Check student balance (should be -10,000.00)
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.balance, Decimal("-10000.00"))

        # Check Cashbox balance (should be 10,000.00)
        cashbox = Cashbox.objects.filter(organization=self.org1).first()
        self.assertIsNotNone(cashbox)
        self.assertEqual(cashbox.balance, Decimal("10000.00"))

        # Check Transaction was created
        tx = Transaction.objects.filter(description__startswith=f"Davomat #{att.id}:").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("10000.00"))
        self.assertEqual(tx.type, "INCOME")

        # 7. Update attendance status to 'absent'
        att.status = "absent"
        att.save()

        # Check student balance restored to 0
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.balance, Decimal("0.00"))

        # Check Cashbox balance goes back to 0
        cashbox.refresh_from_db()
        self.assertEqual(cashbox.balance, Decimal("0.00"))

        # Check Transaction was deleted
        self.assertFalse(Transaction.objects.filter(description__startswith=f"Davomat #{att.id}:").exists())


class CourseMaterialAndOnlineLessonTests(APITestCase):
    def setUp(self):
        # Create two distinct organizations to test multi-tenancy
        self.org1 = Organization.objects.create(name="Tenant 1")
        self.org2 = Organization.objects.create(name="Tenant 2")

        # Create active subscription for Org 1 and Org 2
        from organizations.models import Subscription, Tariff
        import datetime
        from decimal import Decimal
        today = datetime.date.today()
        default_tariff = Tariff.objects.create(name="Premium", price=Decimal("100.00"), student_limit=0)
        Subscription.objects.create(
            organization=self.org1,
            tariff=default_tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )
        Subscription.objects.create(
            organization=self.org2,
            tariff=default_tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )

        self.admin1 = User.objects.create_user(
            username="admin1",
            password="password123",
            role="admin",
            organization=self.org1
        )
        self.student1 = Student.objects.create(
            organization=self.org1,
            first_name="Alice",
            last_name="Green",
            phone="+998909998877",
            balance=0.00
        )
        self.student1_user = User.objects.create_user(
            username="+998909998877",
            phone="+998909998877",
            password="password123",
            role="student",
            organization=self.org1
        )
        self.course1 = Course.objects.create(
            organization=self.org1,
            name="Math",
            price=150.00,
            duration_weeks=12
        )
        self.course2 = Course.objects.create(
            organization=self.org1,
            name="Physics",
            price=150.00,
            duration_weeks=12
        )
        self.group1 = Group.objects.create(
            organization=self.org1,
            name="Math Group 1",
            course=self.course1
        )
        
        from academics.models import StudentGroup
        StudentGroup.objects.create(
            organization=self.org1,
            student=self.student1,
            group=self.group1
        )

    def test_online_lesson_nullable_group(self):
        """
        Verify that OnlineLesson can be created with group=None (optional group).
        """
        self.client.force_authenticate(user=self.admin1)
        url = reverse('online-lesson-list')

        # Test creating OnlineLesson without group (None)
        data = {
            "title": "Online Intro Lesson",
            "group": None,
            "video_url": "https://youtube.com/watch?v=123",
            "description": "Introduction to online learning",
            "is_published": True
        }
        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['group'])

    def test_course_material_crud_and_isolation(self):
        """
        Verify CourseMaterial CRUD and student role isolation.
        """
        from academics.models import CourseMaterial
        # 1. Create Course Materials
        mat1 = CourseMaterial.objects.create(
            organization=self.org1,
            course=self.course1,
            title="Math Syllabus",
            material_type="file",
            is_published=True
        )
        mat2 = CourseMaterial.objects.create(
            organization=self.org1,
            course=self.course2,
            title="Physics Notes",
            material_type="file",
            is_published=True
        )
        mat3 = CourseMaterial.objects.create(
            organization=self.org1,
            course=self.course1,
            title="Math Draft Notes",
            material_type="text",
            is_published=False
        )

        url = reverse('course-material-list')

        # 2. Admin should see all materials
        self.client.force_authenticate(user=self.admin1)
        response = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

        # 3. Student should only see published materials for enrolled courses (Math)
        self.client.force_authenticate(user=self.student1_user)
        response = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Student enrolled in Math (mat1, mat3 but mat3 is not published)
        # So student should only see mat1 (Math Syllabus)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "Math Syllabus")

        # 4. Student should not be able to create course materials (Read Only)
        create_data = {
            "course": self.course1.id,
            "title": "Cheat Sheet",
            "material_type": "text",
            "is_published": True
        }
        response = self.client.post(f"{url}?org_id={self.org1.id}", data=create_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_group_attendance_id_collision_and_date_parsing(self):
        """
        Verify that POSTing to group attendance endpoint does not treat group_id as an Attendance ID
        even if an Attendance record with that ID exists. Also verify that string date is successfully parsed.
        """
        from academics.models import Attendance
        import datetime
        group_id_to_collide = self.group1.id

        # Ensure there is an Attendance record with ID = group_id_to_collide
        if not Attendance.objects.filter(id=group_id_to_collide).exists():
            Attendance.objects.create(
                id=group_id_to_collide,
                organization=self.org1,
                group=self.group1,
                student=self.student1,
                date=datetime.date(2026, 6, 1),
                status="present"
            )

        self.client.force_authenticate(user=self.admin1)
        url = reverse('group-attendance', kwargs={'group_id': group_id_to_collide})

        # Post request to create a new attendance for group_id_to_collide on "2026-06-29"
        data = {
            "student": self.student1.id,
            "date": "2026-06-29",
            "status": "absent"
        }

        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Ensure that it created a NEW record on date "2026-06-29"
        created_attendance = Attendance.objects.filter(
            group_id=group_id_to_collide,
            student_id=self.student1.id,
            date=datetime.date(2026, 6, 29)
        ).first()

        self.assertIsNotNone(created_attendance)
        self.assertEqual(created_attendance.status, "absent")
        # Ensure the date is a datetime.date object (not string)
        self.assertIsInstance(created_attendance.date, datetime.date)

    def test_group_attendance_grade_and_reason(self):
        """
        Verify that POSTing to group attendance endpoint saves and returns grade and reason.
        """
        self.client.force_authenticate(user=self.admin1)
        url = reverse('group-attendance', kwargs={'group_id': self.group1.id})

        # Post request to create a new attendance with grade and reason
        data = {
            "student": self.student1.id,
            "date": "2026-06-30",
            "status": "excused",
            "grade": 5,
            "reason": "Kasal bo'lib qoldi"
        }

        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['grade'], 5)
        self.assertEqual(response.data['reason'], "Kasal bo'lib qoldi")

        # Verify database record
        from academics.models import Attendance
        import datetime
        att = Attendance.objects.get(group=self.group1, student=self.student1, date=datetime.date(2026, 6, 30))
        self.assertEqual(att.grade, 5)
        self.assertEqual(att.reason, "Kasal bo'lib qoldi")

    def test_excused_attendance_requires_reason(self):
        """
        Verify that POSTing excused status without a reason fails validation.
        """
        self.client.force_authenticate(user=self.admin1)
        url = reverse('group-attendance', kwargs={'group_id': self.group1.id})

        data = {
            "student": self.student1.id,
            "date": "2026-06-29",
            "status": "excused",
            "grade": 4,
            "reason": ""  # empty reason
        }

        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", response.data)

    def test_debtor_student_archiving_flow(self):
        """
        Verify that a debtor student is soft-deleted, is retained in debtor list,
        is excluded from total debt, blocked from lead, and blocked from archive deletion until debt is paid.
        """
        from accounts.models import User
        from academics.models import StudentArchive
        from crm.models import Lead

        # Make student1 a debtor
        self.student1.balance = -150000.00
        self.student1.save()

        self.client.force_authenticate(user=self.admin1)

        # 1. Delete student1 -> Should soft delete and deactivate user
        url = reverse('student-detail', kwargs={'pk': self.student1.id})
        response = self.client.delete(f"{url}?org_id={self.org1.id}&reason=Qarzdor&comment=Uzilmadi")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Student should still exist in Student table (is_archived=True)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_archived)

        # User is deactivated (is_active=False), not deleted
        student_user = User.objects.get(username=self.student1.phone, role="student")
        self.assertFalse(student_user.is_active)

        # StudentArchive entry exists
        archive = StudentArchive.objects.get(phone=self.student1.phone)
        self.assertEqual(archive.reason, "Qarzdor")

        # 2. Debtor students list still contains the student, but summary does not
        debtors_url = reverse('student-debts-list')
        debtors_response = self.client.get(f"{debtors_url}?org_id={self.org1.id}")
        self.assertEqual(debtors_response.status_code, status.HTTP_200_OK)
        # There should be our student in the response
        if isinstance(debtors_response.data, dict) and 'results' in debtors_response.data:
            student_ids = [d['id'] for d in debtors_response.data['results']]
        else:
            student_ids = [d['id'] for d in debtors_response.data]
        self.assertIn(self.student1.id, student_ids)

        # Summary total should exclude archived student
        summary_url = reverse('student-debts-summary')
        summary_response = self.client.get(f"{summary_url}?org_id={self.org1.id}")
        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(summary_response.data['total_student_debts']), 0.0)

        # 3. CRM Lead creation/update with this phone number should be blocked
        lead_url = reverse('lead-list')
        lead_data = {
            "name": "Arxivlangan Qarzdor Lead",
            "phone": self.student1.phone
        }
        lead_response = self.client.post(f"{lead_url}?org_id={self.org1.id}", data=lead_data, format='json')
        self.assertEqual(lead_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("phone" in lead_response.data or "Telefon raqam" in lead_response.data)

        # 4. Deleting archive entry from StudentArchiveViewSet should fail due to active debt
        archive_detail_url = reverse('student-archive-detail', kwargs={'pk': archive.id})
        archive_del_response = self.client.delete(f"{archive_detail_url}?org_id={self.org1.id}")
        self.assertEqual(archive_del_response.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Settle the debt -> should allow deletion
        self.student1.balance = 0.00
        self.student1.save()

        # Delete archive entry again -> should succeed
        archive_del_response2 = self.client.delete(f"{archive_detail_url}?org_id={self.org1.id}")
        self.assertEqual(archive_del_response2.status_code, status.HTTP_204_NO_CONTENT)

        # Student and User should now be completely deleted from the database
        self.assertFalse(Student.objects.filter(id=self.student1.id).exists())
        self.assertFalse(User.objects.filter(username=self.student1.phone, role="student").exists())

    def test_teacher_daily_percentage_salary(self):
        """
        Verify that marking student attendance present/late calculates and records
        the teacher's percentage share daily, and updates TeacherSalaryCalculation.
        """
        from finance.models import StaffSalaryPercent, TeacherSalaryCalculation
        from academics.models import Attendance
        import datetime

        # 1. Create a teacher with 30% salary percent
        percent = StaffSalaryPercent.objects.create(
            organization=self.org1,
            name="30%",
            percent=30.00
        )
        teacher = User.objects.create_user(
            username="teacher_test_salary",
            password="password123",
            role="teacher",
            organization=self.org1,
            salary_percentage=percent
        )

        # 2. Assign teacher to group1
        self.group1.teacher = teacher
        self.group1.save()

        # Set course price to 800,000 UZS
        self.course1.price = 800000.00
        self.course1.save()
        
        # Update existing StudentGroup price to 800,000 UZS
        from academics.models import StudentGroup
        sg = StudentGroup.objects.filter(student=self.student1, group=self.group1).first()
        if sg:
            sg.price = 800000.00
            sg.save()

        # 3. Create attendance -> should trigger charge_attendance
        self.client.force_authenticate(user=self.admin1)
        url = reverse('group-attendance', kwargs={'group_id': self.group1.id})
        data = {
            "student": self.student1.id,
            "date": "2026-07-11",
            "status": "present"
        }
        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Get the attendance id and lesson cost
        att_id = response.data['id']
        att = Attendance.objects.get(id=att_id)
        from academics.models import get_lessons_in_month
        lessons_count = get_lessons_in_month(self.group1, 2026, 7)
        expected_lesson_cost = round(800000.00 / lessons_count, 2)
        expected_teacher_share = round(expected_lesson_cost * 0.30, 2)

        # 4. Check that TeacherSalaryCalculation has correct teacher share
        calc = TeacherSalaryCalculation.objects.get(teacher=teacher, period="2026-07")
        self.assertEqual(float(calc.calculated_amount), expected_teacher_share)
        self.assertEqual(calc.details['attendance_charges'][str(att_id)], str(expected_teacher_share))

        # 5. Update attendance to absent -> should refund
        update_url = reverse('attendance-detail', kwargs={'pk': att_id})
        update_data = {
            "status": "absent"
        }
        update_response = self.client.patch(f"{update_url}?org_id={self.org1.id}", data=update_data, format='json')
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        # Calculation amount should now be 0.00 (refunded)
        calc.refresh_from_db()
        self.assertEqual(float(calc.calculated_amount), 0.00)
        self.assertNotIn(str(att_id), calc.details.get('attendance_charges', {}))

        # 6. Mark present again, and verify that TeacherSalaryCalculateView recalculates correctly
        # Mark present
        self.client.patch(f"{update_url}?org_id={self.org1.id}", data={"status": "present"}, format='json')
        calc.refresh_from_db()
        self.assertEqual(float(calc.calculated_amount), expected_teacher_share)

        # Call TeacherSalaryCalculateView
        calc_view_url = reverse('teacher-salary-calculate')
        calc_view_response = self.client.post(f"{calc_view_url}?org_id={self.org1.id}", data={"period": "2026-07"}, format='json')
        self.assertEqual(calc_view_response.status_code, status.HTTP_201_CREATED)

        # Verify that recalculation matches the expected share
        calc.refresh_from_db()
        self.assertEqual(float(calc.calculated_amount), expected_teacher_share)

    def test_archived_student_excluded_from_group(self):
        """
        Verify that archived students are not returned in group student list APIs or counts.
        """
        # Initially student1 is not archived, check they are included
        self.client.force_authenticate(user=self.admin1)
        
        # Check GroupSerializer students list & count
        group_url = reverse('group-detail', kwargs={'pk': self.group1.id})
        response = self.client.get(f"{group_url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['student_count'], 1)
        self.assertEqual(len(response.data['students']), 1)
        self.assertEqual(response.data['students'][0]['id'], self.student1.id)

        # Check student-groups list API
        sg_list_url = reverse('student-group-list')
        sg_response = self.client.get(f"{sg_list_url}?org_id={self.org1.id}&group={self.group1.id}")
        self.assertEqual(sg_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sg_response.data), 1)

        # Now archive student1
        self.student1.is_archived = True
        self.student1.save()

        # Check GroupSerializer again -> count should be 0, student list empty
        response2 = self.client.get(f"{group_url}?org_id={self.org1.id}")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['student_count'], 0)
        self.assertEqual(len(response2.data['students']), 0)

        # Check student-groups list API again -> should be empty
        sg_response2 = self.client.get(f"{sg_list_url}?org_id={self.org1.id}&group={self.group1.id}")
        self.assertEqual(sg_response2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sg_response2.data), 0)

    def test_import_excel_csv(self):
        """
        Verify that Excel/CSV student import API parses columns and creates students.
        """
        self.client.force_authenticate(user=self.admin1)
        import_url = reverse('student-import-excel')

        # 1. Test CSV Import
        csv_content = (
            "Ism,Familiya,Telefon,Balans,Tug'ilgan sana\n"
            "Vali,Aliyev,+998909876543,-50000,10.05.2010\n"
            "Sardor,Karimov,+998901234567,10000,2008-12-05\n"
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_file = SimpleUploadedFile("students.csv", csv_content.encode('utf-8'), content_type="text/csv")

        response = self.client.post(
            f"{import_url}?org_id={self.org1.id}",
            data={'file': csv_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['success_count'], 2)
        self.assertEqual(len(response.data['errors']), 0)

        # Verify students created
        from academics.models import Student
        vali = Student.objects.get(phone="+998909876543", organization=self.org1)
        self.assertEqual(vali.first_name, "Vali")
        self.assertEqual(vali.last_name, "Aliyev")
        self.assertEqual(float(vali.balance), -50000.00)
        self.assertEqual(vali.birth_date.isoformat(), "2010-05-10")

        sardor = Student.objects.get(phone="+998901234567", organization=self.org1)
        self.assertEqual(sardor.first_name, "Sardor")
        self.assertEqual(sardor.birth_date.isoformat(), "2008-12-05")

        # 2. Test XLSX Import
        import openpyxl
        from io import BytesIO
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Ism", "Familiya", "Telefon", "Balans", "Tug'ilgan sana"])
        ws.append(["Madina", "Rustamova", "+998901113344", "0", "15/08/2009"])
        
        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)
        
        xlsx_file = SimpleUploadedFile("students.xlsx", excel_file.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        response2 = self.client.post(
            f"{import_url}?org_id={self.org1.id}",
            data={'file': xlsx_file},
            format='multipart'
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data['success_count'], 1)

        madina = Student.objects.get(phone="+998901113344", organization=self.org1)
        self.assertEqual(madina.first_name, "Madina")
        self.assertEqual(madina.birth_date.isoformat(), "2009-08-15")

    def test_import_excel_edge_cases_and_fixes(self):
        """
        Verify edge cases:
        1. Single column 'F.I.SH' with Uzbek full names.
        2. Siblings sharing parent phone number - both created, neither deleted/overwritten.
        3. Float phone number and unformatted dates/balance.
        4. SchoolClass linking from 'Sinf' column (e.g. 5-A).
        5. Re-importing an archived student restores them (is_archived=False).
        6. Title row before header row in Excel.
        """
        import openpyxl
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from academics.models import Student, SchoolClass, ClassStudent
        from accounts.models import User

        self.client.force_authenticate(user=self.admin1)
        import_url = reverse('student-import-excel')

        # First, create an archived student to verify unarchiving on re-import
        archived_student = Student.objects.create(
            organization=self.org1,
            first_name="Jasur",
            last_name="Tursunov",
            phone="+998903334455",
            is_archived=True
        )

        wb = openpyxl.Workbook()
        ws = wb.active

        # Row 1: Document title (title header test)
        ws.append(["5-A SINF O'QUVCHILARI RO'YXATI", "", "", "", "", ""])
        # Row 2: Actual column headers
        ws.append(["T/r", "F.I.SH", "Telefon", "Sinf", "Balans", "Tug'ilgan sana"])
        # Row 3: Sibling 1 (F.I.SH in 1 column, shared phone as float, class 5-A)
        ws.append([1, "Qodirov Bobur Rustam o'g'li", 998907778899.0, "5-A", "50 000 so'm", "2011-04-12 00:00:00"])
        # Row 4: Sibling 2 (Same parent phone 998907778899, different name)
        ws.append([2, "Qodirova Zilola", 998907778899, "5-A", 0, "15.08.2013"])
        # Row 5: Re-import of archived student (should unarchive him)
        ws.append([3, "Tursunov Jasur", "+998903334455", "5-A", "-10000", "2010/06/20"])

        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        xlsx_file = SimpleUploadedFile(
            "students_edge_cases.xlsx",
            excel_file.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        response = self.client.post(
            f"{import_url}?org_id={self.org1.id}",
            data={'file': xlsx_file},
            format='multipart'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['success_count'], 3)
        self.assertEqual(len(response.data['errors']), 0)

        # 1. Verify Bobur is created
        bobur = Student.objects.filter(phone="+998907778899", first_name="Bobur", organization=self.org1).first()
        self.assertIsNotNone(bobur)
        self.assertEqual(bobur.last_name, "Qodirov")
        self.assertEqual(bobur.father_name, "Rustam o'g'li")
        self.assertEqual(float(bobur.balance), 50000.00)
        self.assertEqual(bobur.birth_date.isoformat(), "2011-04-12")

        # 2. Verify Zilola is ALSO created (not overwriting Bobur!)
        zilola = Student.objects.filter(phone="+998907778899", first_name="Zilola", organization=self.org1).first()
        self.assertIsNotNone(zilola)
        self.assertEqual(zilola.last_name, "Qodirova")
        self.assertNotEqual(bobur.id, zilola.id)

        # Both user accounts exist
        u_bobur = User.objects.filter(first_name="Bobur", role='student').first()
        u_zilola = User.objects.filter(first_name="Zilola", role='student').first()
        self.assertIsNotNone(u_bobur)
        self.assertIsNotNone(u_zilola)
        self.assertNotEqual(u_bobur.id, u_zilola.id)

        # 3. Verify SchoolClass 5-A was created/linked and ClassStudent is active
        sc_5a = SchoolClass.objects.filter(organization=self.org1, grade_level="5", section="A").first()
        self.assertIsNotNone(sc_5a)
        self.assertEqual(bobur.school_class, sc_5a)
        self.assertEqual(zilola.school_class, sc_5a)
        self.assertTrue(ClassStudent.objects.filter(student=bobur, school_class=sc_5a, is_active=True).exists())

        # 4. Verify archived student Jasur was restored
        archived_student.refresh_from_db()
        self.assertFalse(archived_student.is_archived)

    def test_group_attendance_invalid_student(self):
        """
        Verify that posting attendance with a non-existent student ID returns 400 Bad Request
        instead of throwing a 500 error.
        """
        self.client.force_authenticate(user=self.admin1)
        attendance_url = reverse('group-attendance', kwargs={'group_id': self.group1.id})
        
        response = self.client.post(
            f"{attendance_url}?org_id={self.org1.id}",
            data=[{
                "student": 999999,  # Non-existent student ID
                "status": "present",
                "date": "2026-07-11"
            }],
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("bazada topilmadi", response.data['detail'])

    def test_student_send_sms_post_success(self):
        """
        Verify that admin can send SMS to student and it gets saved in SMSMessages.
        """
        self.client.force_authenticate(user=self.admin1)
        url = reverse('student-send-sms', kwargs={'pk': self.student1.id})
        data = {"message": "Test SMS message for student"}
        
        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], "success")
        self.assertIn("SMS successfully sent", response.data['message'])

        # Verify SMS messages count in DB
        from communication.models import SMSMessages
        sms = SMSMessages.objects.filter(recipient=self.student1.phone, organization=self.org1).first()
        self.assertIsNotNone(sms)
        self.assertEqual(sms.message, "Test SMS message for student")
        self.assertEqual(sms.status, "sent")

    def test_student_send_sms_post_teacher_permission(self):
        """
        Verify that teacher can send SMS only if allow_teacher_sms is enabled in subscription.
        """
        from organizations.models import Subscription
        # Get active subscription of Org 1
        sub = Subscription.objects.filter(organization=self.org1, is_active=True).first()
        self.assertIsNotNone(sub)
        
        # 1. By default, teacher cannot send SMS if allow_teacher_sms=False
        sub.allow_teacher_sms = False
        sub.save()

        # Give teacher role permission to access 'Talabalar' page
        self.org1.role_permissions = {
            "teacher": {
                "pages": {
                    "Talabalar": {
                        "create": True,
                        "edit": True,
                        "view": True,
                        "delete": True
                    }
                }
            }
        }
        self.org1.save()

        # Create a teacher user
        teacher = User.objects.create_user(
            username="+998901112270",
            password="securepassword",
            phone="+998901112270",
            role="teacher",
            organization=self.org1
        )
        self.client.force_authenticate(user=teacher)
        url = reverse('student-send-sms', kwargs={'pk': self.student1.id})
        data = {"message": "Hello from teacher"}

        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("O'qituvchilarga talabalarga SMS yuborishga ruxsat berilmagan", response.data['detail'])

        # 2. If allow_teacher_sms is enabled, teacher can send SMS
        sub.allow_teacher_sms = True
        sub.save()

        response = self.client.post(f"{url}?org_id={self.org1.id}", data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], "success")

    def test_student_send_sms_post_invalid(self):
        """
        Verify that sending SMS without a message returns 400 Bad Request.
        """
        self.client.force_authenticate(user=self.admin1)
        url = reverse('student-send-sms', kwargs={'pk': self.student1.id})
        
        response = self.client.post(f"{url}?org_id={self.org1.id}", data={}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], "Message is required.")

    def test_student_send_sms_get_history(self):
        """
        Verify GET on student-send-sms returns correct history with tenant isolation.
        """
        from communication.models import SMSMessages
        # Prepare parent phones
        self.student1.father_phone = "+998909998811"
        self.student1.mother_phone = "+998909998822"
        self.student1.save()

        # Create history messages
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.phone,
            message="Msg to student",
            status='sent'
        )
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.father_phone,
            message="Msg to father",
            status='sent'
        )
        SMSMessages.objects.create(
            organization=self.org1,
            recipient=self.student1.mother_phone,
            message="Msg to mother",
            status='sent'
        )
        # Message for another recipient (should not be in Alice's history)
        SMSMessages.objects.create(
            organization=self.org1,
            recipient="+998901110000",
            message="Msg to other",
            status='sent'
        )
        # Message for Alice's phone but in organization 2 (tenant isolation)
        SMSMessages.objects.create(
            organization=self.org2,
            recipient=self.student1.phone,
            message="Msg in Org 2",
            status='sent'
        )

        self.client.force_authenticate(user=self.admin1)
        url = reverse('student-send-sms', kwargs={'pk': self.student1.id})

        response = self.client.get(f"{url}?org_id={self.org1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['student']['id'], self.student1.id)
        self.assertEqual(response.data['total_count'], 3)
        
        # Verify messages in response
        messages = [item['message'] for item in response.data['sms_history']]
        self.assertIn("Msg to student", messages)
        self.assertIn("Msg to father", messages)
        self.assertIn("Msg to mother", messages)
        self.assertNotIn("Msg to other", messages)
        self.assertNotIn("Msg in Org 2", messages)


class StudentGroupLeaveTests(APITestCase):
    def test_student_group_leave_student_null_fallback(self):
        """
        Ensure that when a student is deleted and student ForeignKey becomes NULL,
        StudentGroupLeave API serializer falls back to student_name and student_phone.
        """
        from academics.models import Student, Group, Course, StudentGroupLeave
        from organizations.models import Organization
        from academics.serializers import StudentGroupLeaveSerializer
        
        org = Organization.objects.create(name="Test Org")
        course = Course.objects.create(
            organization=org,
            name="Mathematics",
            price=120.00,
            duration_weeks=16
        )
        student = Student.objects.create(
            organization=org,
            first_name="Alice",
            last_name="Green",
            phone="+998909998877",
            balance=0.00
        )
        group = Group.objects.create(
            organization=org,
            name="Math 101",
            course=course
        )
        
        leave = StudentGroupLeave.objects.create(
            organization=org,
            student=student,
            group=group,
            leave_date="2026-07-15",
            comment="Leaving math"
        )
        
        # Verify save() auto-populated
        self.assertEqual(leave.student_name, "Alice Green")
        self.assertEqual(leave.student_phone, "+998909998877")
        
        # Hard delete student
        student.delete()
        leave.refresh_from_db()
        self.assertIsNone(leave.student)
        self.assertEqual(leave.student_name, "Alice Green")
        
        # Verify serializer fallback representation
        serializer = StudentGroupLeaveSerializer(leave)
        data = serializer.data
        self.assertEqual(data['student']['id'], None)
        self.assertEqual(data['student']['full_name'], "Alice Green")
        self.assertEqual(data['student']['phone_number'], "+998909998877")

    def test_student_phone_validation_and_cleaning(self):
        """
        Verify that student phone numbers are formatted and validated correctly.
        """
        from academics.serializers import StudentSerializer
        
        # 1. 9-digit phone is standardly formatted to +998XXXXXXXXX
        serializer = StudentSerializer(data={
            "first_name": "Vali",
            "phone": "901234567",
            "password": "password123"
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone"], "+998901234567")
        
        # 2. Invalid format raises validation error
        serializer2 = StudentSerializer(data={
            "first_name": "Vali",
            "phone": "+998",
            "password": "password123"
        })
        self.assertFalse(serializer2.is_valid())
        self.assertIn("phone", serializer2.errors)
        self.assertEqual(serializer2.errors["phone"][0], "Telefon raqami noto'g'ri formatda. Loyihada O'zbekiston raqamlari (+998XXXXXXXXX) qabul qilinadi.")


class NewAcademicsAndStudentsAPITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Smart Test Org")
        from organizations.models import Subscription, Tariff, Branch
        from decimal import Decimal
        import datetime
        today = datetime.date.today()
        default_tariff = Tariff.objects.create(name="Premium", price=Decimal("100.00"), student_limit=0)
        Subscription.objects.create(
            organization=self.org,
            tariff=default_tariff,
            start_date=today,
            end_date=today + datetime.timedelta(days=365),
            is_active=True
        )
        self.branch = Branch.objects.create(name="Main Branch", organization=self.org)
        self.admin_user = User.objects.create_user(
            username="admin_user",
            password="password123",
            role="admin",
            organization=self.org,
            branch=self.branch
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_user",
            first_name="Olim",
            last_name="Hasanov",
            password="password123",
            role="teacher",
            organization=self.org,
            branch=self.branch
        )
        from academics.models import Room, Course, Student, Group
        self.room = Room.objects.create(name="101-Xona", capacity=25, organization=self.org, branch=self.branch)
        self.course = Course.objects.create(
            name="Matematika",
            price=Decimal("300000.00"),
            duration_weeks=12,
            color="#FF5733",
            is_active=True,
            organization=self.org,
            branch=self.branch
        )
        self.group = Group.objects.create(
            name="Math-01",
            course=self.course,
            room=self.room,
            teacher=self.teacher_user,
            organization=self.org,
            branch=self.branch
        )
        self.student1 = Student.objects.create(
            first_name="Anvar",
            last_name="Karimov",
            phone="+998901112233",
            balance=Decimal("50000.00"),
            organization=self.org,
            branch=self.branch
        )
        self.student2 = Student.objects.create(
            first_name="Jasur",
            last_name="Aliyev",
            phone="+998904445566",
            balance=Decimal("0.00"),
            organization=self.org,
            branch=self.branch
        )
        self.client.force_authenticate(user=self.admin_user)

    def test_buildings_api(self):
        # Create building
        res = self.client.post('/api/v1/academics/buildings/', {
            "branch": self.branch.id,
            "name": "1-Bino (Asosiy)",
            "address": "Chilonzor ko'chasi, 5-uy",
            "capacity": 350
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['name'], "1-Bino (Asosiy)")
        b_id = res.data['id']

        # List buildings
        list_res = self.client.get('/api/v1/academics/buildings/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

    def test_classes_and_student_actions_api(self):
        # Create Class
        res = self.client.post('/api/v1/academics/classes/', {
            "branch": self.branch.id,
            "grade_level": "4",
            "section": "A",
            "language": "uz",
            "teacher": self.teacher_user.id,
            "room": self.room.id,
            "academic_year": "2026-2027"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        class_id = res.data['id']
        self.assertEqual(res.data['name'], "4-A")
        self.assertEqual(res.data['teacher_name'], "Olim Hasanov")

        # Create target class for transfer
        res_target = self.client.post('/api/v1/academics/classes/', {
            "branch": self.branch.id,
            "grade_level": "4",
            "section": "B",
            "language": "uz",
            "academic_year": "2026-2027"
        })
        target_class_id = res_target.data['id']

        # Add students to 4-A
        add_res = self.client.post(f'/api/v1/academics/classes/{class_id}/add-students/', {
            "student_ids": [self.student1.id, self.student2.id]
        }, format='json')
        self.assertEqual(add_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(add_res.data['added_students']), 2)

        # Get students of 4-A
        st_res = self.client.get(f'/api/v1/academics/classes/{class_id}/students/')
        self.assertEqual(st_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(st_res.data), 2)
        self.assertEqual(st_res.data[0]['full_name'], "Anvar Karimov")

        # Transfer student1 to 4-B
        transfer_res = self.client.post(f'/api/v1/academics/classes/{class_id}/transfer-student/', {
            "student_id": self.student1.id,
            "target_class_id": target_class_id
        })
        self.assertEqual(transfer_res.status_code, status.HTTP_200_OK)

        # Verify student counts after transfer
        st_res_source = self.client.get(f'/api/v1/academics/classes/{class_id}/students/')
        self.assertEqual(len(st_res_source.data), 1)

        st_res_target = self.client.get(f'/api/v1/academics/classes/{target_class_id}/students/')
        self.assertEqual(len(st_res_target.data), 1)
        self.assertEqual(st_res_target.data[0]['student_id'], self.student1.id)

    def test_parents_api(self):
        # Create parent via /api/v1/students/parents/
        res = self.client.post('/api/v1/students/parents/', {
            "student": self.student1.id,
            "full_name": "Karimov Rustam",
            "relation": "father",
            "phone": "+998901234567",
            "extra_phone": "+998934567890",
            "workplace": "IT Park",
            "address": "Yunusobod 14",
            "comment": "Faol ota-ona"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['student_name'], "Anvar Karimov")

        # Also list via /api/v1/academics/parents/
        list_res = self.client.get('/api/v1/academics/parents/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

    def test_student_address_api(self):
        # Create address via /api/v1/students/addresses/
        res = self.client.post('/api/v1/students/addresses/', {
            "student": self.student1.id,
            "region": "Toshkent shahri",
            "district": "Yunusobod tumani",
            "address": "14-mavze, 22-uy, 45-xonadon",
            "parent_name": "Karimov Rustam",
            "parent_phone": "+998901234567",
            "student_phone": "+998901112233",
            "notes": "Markazga yaqin"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['district'], "Yunusobod tumani")

        # List via /api/v1/students/addresses/
        list_res = self.client.get('/api/v1/students/addresses/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

    def test_homework_and_courses_api(self):
        import datetime
        from django.utils import timezone
        deadline = timezone.now() + datetime.timedelta(days=2)

        # Create Homework via /api/v1/academics/homework/
        hw_res = self.client.post('/api/v1/academics/homework/', {
            "group": self.group.id,
            "teacher": self.teacher_user.id,
            "title": "Kvadrat tenglamalar",
            "description": "1-10 mashqlarni yechish",
            "deadline": deadline.isoformat()
        })
        self.assertEqual(hw_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(hw_res.data['teacher_name'], "Olim Hasanov")
        self.assertEqual(hw_res.data['group_name'], "Math-01")

        # Course color and is_active check
        course_res = self.client.get(f'/api/v1/academics/courses/{self.course.id}/')
        self.assertEqual(course_res.status_code, status.HTTP_200_OK)
        self.assertEqual(course_res.data['color'], "#FF5733")
        self.assertTrue(course_res.data['is_active'])

    def test_student_school_class_create_update_and_filter(self):
        from academics.models import SchoolClass, ClassStudent, Student

        # 1. Create a SchoolClass
        school_class = SchoolClass.objects.create(
            organization=self.org,
            branch=self.branch,
            grade_level="5",
            section="B",
            language="uz",
            academic_year="2026-2027"
        )

        # 2. Create a new Student with school_class
        res = self.client.post('/api/v1/academics/students/', {
            "first_name": "Sardor",
            "last_name": "Rahimov",
            "phone": "+998905556677",
            "password": "password123",
            "school_class": school_class.id
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['school_class'], school_class.id)
        self.assertEqual(res.data['school_class_name'], "5-B")
        self.assertEqual(res.data['class_name'], "5-B")
        self.assertEqual(res.data['school_class_detail']['grade_level'], "5")
        student_id = res.data['id']

        # Verify ClassStudent was automatically created
        self.assertTrue(
            ClassStudent.objects.filter(student_id=student_id, school_class=school_class, is_active=True).exists()
        )

        # 3. Filter students by school_class
        filter_res = self.client.get(f'/api/v1/academics/students/?school_class={school_class.id}')
        self.assertEqual(filter_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filter_res.data), 1)
        self.assertEqual(filter_res.data[0]['id'], student_id)

        # 4. Update student class to another class
        school_class_6a = SchoolClass.objects.create(
            organization=self.org,
            branch=self.branch,
            grade_level="6",
            section="A",
            language="uz",
            academic_year="2026-2027"
        )

        patch_res = self.client.patch(f'/api/v1/academics/students/{student_id}/', {
            "school_class": school_class_6a.id
        })
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['school_class'], school_class_6a.id)
        self.assertEqual(patch_res.data['school_class_name'], "6-A")

        # Verify previous class is inactive and new class is active in ClassStudent
        self.assertTrue(
            ClassStudent.objects.filter(student_id=student_id, school_class=school_class_6a, is_active=True).exists()
        )
        self.assertTrue(
            ClassStudent.objects.filter(student_id=student_id, school_class=school_class, is_active=False).exists()
        )


class StudentAppealTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Appeal Test Org", subdomain="appeal-org")
        self.branch = Branch.objects.create(name="Main Branch", organization=self.org)
        self.owner = User.objects.create_user(
            username="appeal_owner",
            password="password123",
            role="owner",
            organization=self.org,
            telegram_chat_id="999888777"
        )
        self.student = Student.objects.create(
            first_name="Ali",
            last_name="Valiyev",
            phone="+998901112233",
            telegram_chat_id="123456789",
            organization=self.org,
            branch=self.branch
        )
        self.client.force_authenticate(user=self.owner)

    @patch('academics.telegram_bot.send_telegram_message')
    def test_student_submits_appeal_via_telegram_bot(self, mock_send):
        mock_send.return_value = True
        from academics.telegram_bot import handle_telegram_update, STUDENT_BOT_TOKEN
        from academics.models import StudentAppeal
        from communication.models import Notification

        # 1. Student taps '✍️ Murojaat yuborish'
        update_start = {
            "message": {
                "chat": {"id": 123456789},
                "text": "✍️ Murojaat yuborish"
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, update_start)
        mock_send.assert_called()

        # 2. Student selects '🔴 Shikoyat'
        update_type = {
            "message": {
                "chat": {"id": 123456789},
                "text": "🔴 Shikoyat"
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, update_type)

        # 3. Student sends the complaint text
        complaint_text = "Dars xonalarida konditsioner ishlamayapti, juda issiq!"
        update_text = {
            "message": {
                "chat": {"id": 123456789},
                "text": complaint_text
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, update_text)

        # Verify StudentAppeal created
        appeal = StudentAppeal.objects.filter(student=self.student).first()
        self.assertIsNotNone(appeal)
        self.assertEqual(appeal.appeal_type, 'complaint')
        self.assertEqual(appeal.message, complaint_text)
        self.assertEqual(appeal.status, 'pending')
        self.assertFalse(appeal.is_escalated_to_owner)

        # Verify Notification created in CRM
        notif = Notification.objects.filter(organization=self.org, type='student_appeal').first()
        self.assertIsNotNone(notif)
        self.assertIn("Ali", notif.title)
        self.assertIn(complaint_text, notif.message)

        # 4. Student checks '📋 Murojaatlarim'
        update_check = {
            "message": {
                "chat": {"id": 123456789},
                "text": "📋 Murojaatlarim"
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, update_check)
        self.assertIn("Kutilmoqda", mock_send.call_args[0][2])

    @patch('academics.telegram_bot.send_telegram_message')
    def test_7_day_escalation_to_owner(self, mock_send):
        mock_send.return_value = True
        from academics.tasks import check_and_escalate_unresolved_appeals
        from academics.models import StudentAppeal
        from datetime import timedelta
        from django.utils import timezone

        # 1. Create an appeal that was submitted 8 days ago (overdue)
        overdue_appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='complaint',
            message="Kutubxona kitoblari yetishmayapti",
            status='pending',
            is_escalated_to_owner=False
        )
        StudentAppeal.objects.filter(id=overdue_appeal.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        # 2. Create another recent appeal (2 days ago, not overdue)
        recent_appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='suggestion',
            message="Yangi shaxmat to'garagi ochilsa yaxshi bo'lardi",
            status='pending',
            is_escalated_to_owner=False
        )
        StudentAppeal.objects.filter(id=recent_appeal.id).update(
            created_at=timezone.now() - timedelta(days=2)
        )

        # 3. Create a resolved appeal (8 days ago, but already resolved so no escalation)
        resolved_appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='request',
            message="Sertifikat olishim kerak edi",
            status='resolved',
            is_escalated_to_owner=False
        )
        StudentAppeal.objects.filter(id=resolved_appeal.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        # Run the escalation task
        escalated_count = check_and_escalate_unresolved_appeals()
        self.assertEqual(escalated_count, 1)

        # Verify overdue appeal is marked escalated
        overdue_appeal.refresh_from_db()
        self.assertTrue(overdue_appeal.is_escalated_to_owner)
        self.assertIsNotNone(overdue_appeal.escalated_at)

        # Verify telegram message was sent to owner's chat_id
        mock_send.assert_called()
        call_args = mock_send.call_args[0]
        self.assertEqual(call_args[1], "999888777")  # owner's chat_id
        self.assertIn("7 KUNDAN BUYON QABUL QILINMAGAN MUROJAAT", call_args[2])
        self.assertIn("Kutubxona kitoblari yetishmayapti", call_args[2])

        # Recent and resolved should NOT be escalated
        recent_appeal.refresh_from_db()
        self.assertFalse(recent_appeal.is_escalated_to_owner)
        resolved_appeal.refresh_from_db()
        self.assertFalse(resolved_appeal.is_escalated_to_owner)

        # Running again shouldn't re-send already escalated appeals
        second_run_count = check_and_escalate_unresolved_appeals()
        self.assertEqual(second_run_count, 0)

    @patch('academics.telegram_bot.send_telegram_message')
    def test_student_appeal_api_accept_and_resolve(self, mock_send):
        mock_send.return_value = True
        from academics.models import StudentAppeal

        appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='complaint',
            message="O'qituvchi darsga kechikib keldi",
            status='pending'
        )

        # 1. List appeals
        res = self.client.get('/api/v1/academics/student-appeals/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)

        # 2. Accept appeal
        accept_res = self.client.post(f'/api/v1/academics/student-appeals/{appeal.id}/accept/')
        self.assertEqual(accept_res.status_code, status.HTTP_200_OK)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, 'in_progress')
        self.assertEqual(appeal.responded_by, self.owner)

        # 3. Resolve appeal
        resolve_res = self.client.post(
            f'/api/v1/academics/student-appeals/{appeal.id}/resolve/',
            {'response': "O'qituvchi bilan tushuntirish ishlari olib borildi.", 'status': 'resolved'}
        )
        self.assertEqual(resolve_res.status_code, status.HTTP_200_OK)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, 'resolved')
        self.assertEqual(appeal.response, "O'qituvchi bilan tushuntirish ishlari olib borildi.")

    @patch('academics.telegram_bot.send_telegram_message')
    def test_3_day_satisfaction_poll_sent_to_student(self, mock_send):
        mock_send.return_value = True
        from academics.tasks import check_and_send_appeal_satisfaction_polls
        from academics.models import StudentAppeal
        from datetime import timedelta
        from django.utils import timezone

        # Create appeal from 4 days ago
        appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='complaint',
            message="Xonada partalar yetarli emas",
            status='in_progress',
            satisfaction_poll_sent=False
        )
        StudentAppeal.objects.filter(id=appeal.id).update(
            created_at=timezone.now() - timedelta(days=4)
        )

        sent_count = check_and_send_appeal_satisfaction_polls()
        self.assertEqual(sent_count, 1)

        appeal.refresh_from_db()
        self.assertTrue(appeal.satisfaction_poll_sent)
        self.assertIsNotNone(appeal.satisfaction_poll_sent_at)

        # Verify telegram message sent to student
        mock_send.assert_called()
        call_args = mock_send.call_args[0]
        self.assertEqual(call_args[1], "123456789")  # student's telegram chat_id
        self.assertIn("muammoingiz ma'muriyat tomonidan ko'rib chiqildimi / hal qilindimi", call_args[2])

        # Check inline keyboard has yes/no callbacks
        kwargs = mock_send.call_args[1]
        inline_markup = kwargs.get('reply_markup')
        self.assertIsNotNone(inline_markup)
        buttons = inline_markup['inline_keyboard'][0]
        self.assertEqual(buttons[0]['callback_data'], f"appeal_satisfaction_yes_{appeal.id}")
        self.assertEqual(buttons[1]['callback_data'], f"appeal_satisfaction_no_{appeal.id}")

    @patch('academics.telegram_bot.send_telegram_message')
    def test_student_confirms_resolved_yes(self, mock_send):
        mock_send.return_value = True
        from academics.telegram_bot import handle_telegram_update, STUDENT_BOT_TOKEN
        from academics.models import StudentAppeal

        appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='complaint',
            message="Konditsioner pulti yo'q",
            status='in_progress'
        )

        # Simulate student clicking '✅ Ha, hal bo'ldi'
        callback_update = {
            "callback_query": {
                "id": "cb_111",
                "from": {"id": 123456789},
                "data": f"appeal_satisfaction_yes_{appeal.id}",
                "message": {"chat": {"id": 123456789}}
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, callback_update)

        appeal.refresh_from_db()
        self.assertTrue(appeal.student_satisfied)
        self.assertEqual(appeal.status, 'resolved')
        self.assertIsNotNone(appeal.satisfaction_responded_at)
        self.assertFalse(appeal.is_escalated_to_owner)

        # Student gets thank you message
        mock_send.assert_called()
        self.assertIn("hal bo'lganidan juda xursandmiz", mock_send.call_args[0][2])

    @patch('academics.telegram_bot.send_telegram_message')
    def test_student_confirms_not_resolved_no_escalates_to_owner_with_teacher_and_group(self, mock_send):
        mock_send.return_value = True
        from academics.telegram_bot import handle_telegram_update, STUDENT_BOT_TOKEN
        from academics.models import StudentAppeal, Course, Group, StudentGroup

        # Create teacher, course and group for the student
        teacher = User.objects.create_user(
            username="math_teacher",
            first_name="Sardor",
            last_name="Rahimov",
            role="teacher",
            organization=self.org
        )
        course = Course.objects.create(name="Algebra", organization=self.org, price=100.0)
        group = Group.objects.create(name="Algebra 101", course=course, teacher=teacher, organization=self.org, status='active')
        StudentGroup.objects.create(student=self.student, group=group, organization=self.org)

        appeal = StudentAppeal.objects.create(
            student=self.student,
            organization=self.org,
            branch=self.branch,
            appeal_type='complaint',
            message="O'qituvchi dars mavzusini tushuntirib bermadi",
            status='in_progress'
        )

        # Simulate student clicking '❌ Yo'q, hal bo'lmadi'
        callback_update = {
            "callback_query": {
                "id": "cb_222",
                "from": {"id": 123456789},
                "data": f"appeal_satisfaction_no_{appeal.id}",
                "message": {"chat": {"id": 123456789}}
            }
        }
        handle_telegram_update('student', STUDENT_BOT_TOKEN, callback_update)

        appeal.refresh_from_db()
        self.assertFalse(appeal.student_satisfied)
        self.assertTrue(appeal.is_escalated_to_owner)
        self.assertIsNotNone(appeal.escalated_at)

        # Verify alert was sent to organization owner
        self.assertGreaterEqual(mock_send.call_count, 2)  # student ack + owner alert
        owner_call = [call for call in mock_send.call_args_list if call[0][1] == "999888777"][0]
        owner_alert_text = owner_call[0][2]

        self.assertIn("HAL QILINMAGAN TALABA SHIKOYATI", owner_alert_text)
        self.assertIn("Ali Valiyev", owner_alert_text)
        self.assertIn("Sardor Rahimov", owner_alert_text)  # Teacher name
        self.assertIn("Algebra 101", owner_alert_text)     # Group name
        self.assertIn("O'qituvchi dars mavzusini tushuntirib bermadi", owner_alert_text)
        self.assertIn("Muammo hal bo'lmadi", owner_alert_text)










