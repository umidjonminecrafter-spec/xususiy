from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization

User = get_user_model()

class AccountsAPITests(APITestCase):
    def test_register_creates_user_and_organization(self):
        """
        Ensure user registration works and automatically creates a new organization.
        """
        url = reverse('account-register')
        data = {
            "password": "testpassword123",
            "email": "owner@talim.com",
            "phone": "+998901112233",
            "full_name": "John Doe",
            "organization_name": "John's Academy"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('user', response.data)
        org_id = response.data['user']['organization']
        self.assertEqual(response.data['user']['username'], f"+998901112233_{org_id}")
        
        # Verify organization is created
        org_name = response.data['user']['organization_name']
        self.assertEqual(org_name, "John's Academy")
        self.assertTrue(Organization.objects.filter(name="John's Academy").exists())

    def test_login_returns_token_and_user_info(self):
        """
        Ensure login validates credentials and returns tokens.
        """
        org = Organization.objects.create(name="Login Test Org")
        User.objects.create_user(
            username="+998901112234",
            password="securepassword",
            email="test@talim.com",
            phone="+998901112234",
            role="owner",
            organization=org
        )
        
        url = reverse('account-login')
        data = {
            "username": "+998901112234",
            "password": "securepassword"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['username'], '+998901112234')

    def test_profile_update_photo(self):
        """
        Ensure user profile photo can be updated via PATCH request.
        """
        org = Organization.objects.create(name="Profile Test Org")
        user = User.objects.create_user(
            username="+998901112235",
            password="securepassword",
            email="test@talim.com",
            phone="+998901112235",
            role="employee",
            organization=org
        )
        self.client.force_authenticate(user=user)
        
        # Create a mock image file
        from django.core.files.uploadedfile import SimpleUploadedFile
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9'
            b'\x04\x01\x0a\x00\x01\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x02\x02\x4c\x01\x00\x3b'
        )
        photo = SimpleUploadedFile('avatar.gif', small_gif, content_type='image/gif')
        
        url = reverse('account-profile')
        response = self.client.patch(url, {'photo': photo}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['photo'])

    def test_employee_multi_branch_assignment(self):
        """
        Ensure staff can be assigned to multiple branches and it's reflected correctly.
        """
        org = Organization.objects.create(name="Multi Branch Test Org")
        from organizations.models import Branch
        branch1 = Branch.objects.create(name="Branch 1", organization=org)
        branch2 = Branch.objects.create(name="Branch 2", organization=org)
        
        staff = User.objects.create_user(
            username="+998901112299",
            password="securepassword",
            email="staff@talim.com",
            phone="+998901112299",
            role="admin",
            organization=org
        )
        
        staff.branches.set([branch1, branch2])
        staff.branch = branch1
        staff.save()
        
        self.assertEqual(staff.branches.count(), 2)
        self.assertIn(branch1, staff.branches.all())
        self.assertIn(branch2, staff.branches.all())

    def test_employee_unique_phone_validation(self):
        """
        Verify that creating an employee with an existing phone number returns a 400 validation error
        specifically under the 'phone' key if in the SAME organization, but passes for DIFFERENT organizations.
        """
        from accounts.serializers import EmployeeSerializer
        org = Organization.objects.create(name="Unique Phone Org")
        
        # Pre-create user in org
        User.objects.create_user(
            username="+998901112288_1",
            password="password123",
            phone="+998901112288",
            role="employee",
            organization=org
        )
        
        class MockRequest:
            def __init__(self, user):
                self.user = user
                
        admin_user = User.objects.create_user(
            username="admin_user",
            password="password",
            organization=org,
            role="admin"
        )
        mock_request = MockRequest(admin_user)
        
        # Creating employee in same organization should fail
        serializer = EmployeeSerializer(
            data={
                "first_name": "Bob",
                "phone": "+998901112288",
                "role": "employee",
                "position": "Manager"
            },
            context={"request": mock_request}
        )
        
        self.assertFalse(serializer.is_valid())
        self.assertIn("phone", serializer.errors)
        self.assertEqual(serializer.errors["phone"][0], "Ushbu telefon raqamli xodim tizimda allaqachon ro'yxatdan o'tgan.")
        
        # Creating employee in different organization should succeed
        org2 = Organization.objects.create(name="Second Org")
        admin_user2 = User.objects.create_user(
            username="admin_user2",
            password="password",
            organization=org2,
            role="admin"
        )
        mock_request2 = MockRequest(admin_user2)
        
        serializer2 = EmployeeSerializer(
            data={
                "first_name": "Bob",
                "phone": "+998901112288",
                "role": "employee",
                "position": "Manager"
            },
            context={"request": mock_request2}
        )
        self.assertTrue(serializer2.is_valid(), serializer2.errors)

    def test_employee_serializer_includes_groups(self):
        """
        Verify that EmployeeSerializer serializes the teacher's groups and groups_detail.
        """
        from accounts.serializers import EmployeeSerializer
        from academics.models import Group, Course
        
        org = Organization.objects.create(name="Groups Test Org")
        teacher = User.objects.create_user(
            username="+998901112277_1",
            password="password123",
            phone="+998901112277",
            role="teacher",
            organization=org
        )
        
        course = Course.objects.create(
            organization=org,
            name="Chemistry",
            price=150.00,
            duration_weeks=10
        )
        
        group1 = Group.objects.create(
            organization=org,
            name="Chem 101",
            course=course,
            teacher=teacher
        )
        
        serializer = EmployeeSerializer(teacher)
        data = serializer.data
        self.assertIn("groups", data)
        self.assertIn("groups_detail", data)
        self.assertEqual(data["groups"], [group1.id])
        self.assertEqual(data["groups_detail"], [{"id": group1.id, "name": "Chem 101"}])

