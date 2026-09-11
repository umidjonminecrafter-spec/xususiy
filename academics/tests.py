from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization
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
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 0)

        # Authenticate as user of Org 1, request without org_id -> falls back to user org (Org 1) -> returns Alice
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['first_name'], "Alice")

        # Authenticate as user of Org 1, and explicitly request Org 2.
        # Since self.user1 is NOT a superuser, the override is ignored, and it falls back to Org 1 -> returns Alice (NOT Bob)
        response = self.client.get(f"{url}?org_id={self.org2.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['first_name'], "Alice")

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
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['first_name'], "Bob")

        # Superuser requests specifying Org 1 explicitly via header -> returns Alice
        response = self.client.get(url, HTTP_X_ORG_ID=str(self.org1.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['first_name'], "Alice")

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

        # Check Cashbox balance (should be 0.00 since student attendance billing does not affect cashbox balance)
        cashbox = Cashbox.objects.filter(organization=self.org1).first()
        self.assertIsNotNone(cashbox)
        self.assertEqual(cashbox.balance, Decimal("0.00"))

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
        CourseMaterial.objects.create(
            organization=self.org1,
            course=self.course1,
            title="Math Syllabus",
            material_type="file",
            is_published=True
        )
        CourseMaterial.objects.create(
            organization=self.org1,
            course=self.course2,
            title="Physics Notes",
            material_type="file",
            is_published=True
        )
        CourseMaterial.objects.create(
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


class StudentImportHelperUnitTests(APITestCase):
    """
    Unit tests for isolated student import helper functions.
    """
    def setUp(self):
        self.org = Organization.objects.create(name="Import Helper Org")

    def test_normalize_student_row(self):
        from academics.services.student_import import normalize_student_row
        row = {
            "ism": "Sardor",
            "familiya": "Rahimov",
            "telefon": "+998901234567",
            "balans": "50000"
        }
        normalized = normalize_student_row(row)
        self.assertEqual(normalized['first_name'], "Sardor")
        self.assertEqual(normalized['last_name'], "Rahimov")
        self.assertEqual(normalized['phone'], "+998901234567")
        self.assertEqual(normalized['balance'], "50000")

    def test_sanitize_student_data(self):
        from academics.services.student_import import sanitize_student_data
        data = {
            "first_name": "Nodir",
            "phone": "99890 123-45-67",
            "birth_date": "15.06.2005"
        }
        sanitized = sanitize_student_data(data, org_id=self.org.id)
        self.assertEqual(sanitized['organization'], self.org.id)
        self.assertEqual(sanitized['phone'], "+998901234567")
        self.assertEqual(sanitized['birth_date'], "2005-06-15")

    def test_parse_student_import_file_csv(self):
        from academics.services.student_import import parse_student_import_file
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_content = "Ism,Familiya,Telefon\nAnvar,Saidov,+998901112233\n"
        csv_file = SimpleUploadedFile("students.csv", csv_content.encode('utf-8'), content_type="text/csv")
        rows = parse_student_import_file(csv_file)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ism'], "Anvar")
        self.assertEqual(rows[0]['familiya'], "Saidov")
        self.assertEqual(rows[0]['telefon'], "+998901112233")








