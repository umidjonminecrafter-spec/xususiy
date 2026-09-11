from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from organizations.models import Organization, Branch
from tasks.models import Board, Column, Item, TaskHistory

User = get_user_model()

class TaskHistoryTests(APITestCase):
    def setUp(self):
        # Create organization
        self.org = Organization.objects.create(name="Test Org")
        self.branch = Branch.objects.create(name="Test Branch", organization=self.org)
        
        # Create user
        self.user = User.objects.create_user(
            username="testuser",
            password="password123",
            first_name="Ali",
            last_name="Valiyev",
            role="owner",
            organization=self.org,
            branch=self.branch
        )
        self.client.force_authenticate(user=self.user)
        
        # Create board and column
        self.board = Board.objects.create(name="Project Board", organization=self.org, branch=self.branch)
        self.column1 = Column.objects.create(name="To Do", board=self.board, organization=self.org, branch=self.branch, order=1)
        self.column2 = Column.objects.create(name="In Progress", board=self.board, organization=self.org, branch=self.branch, order=2)

    def test_task_creation_logs_history(self):
        url = reverse('item-list')
        data = {
            "board": self.board.id,
            "column": self.column1.id,
            "title": "Yangi Vazifa",
            "description": "Batafsil ma'lumot"
        }
        
        response = self.client.post(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check if TaskHistory is created
        item_id = response.data['id']
        history = TaskHistory.objects.filter(item_id=item_id)
        self.assertEqual(history.count(), 1)
        
        record = history.first()
        self.assertEqual(record.action, "created")
        self.assertEqual(record.user, self.user)
        self.assertIn("Yangi vazifa yaratildi", record.details)
        self.assertIn("Yangi Vazifa", record.details)

    def test_task_update_logs_history(self):
        # Create task
        item = Item.objects.create(
            board=self.board,
            column=self.column1,
            title="Eski Vazifa",
            description="Eski Tavsif",
            organization=self.org,
            branch=self.branch
        )
        
        url = reverse('item-detail', kwargs={'pk': item.id})
        data = {
            "title": "Yangilangan Vazifa",
            "description": "Yangi Tavsif",
            "is_completed": True
        }
        
        response = self.client.patch(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check if TaskHistory logs updates
        history = TaskHistory.objects.filter(item=item, action="updated")
        self.assertEqual(history.count(), 1)
        
        record = history.first()
        self.assertIn("nomi o'zgartirildi", record.details)
        self.assertIn("tavsifi o'zgartirildi", record.details)
        self.assertIn("holati 'bajarildi' deb belgilandi", record.details)

    def test_task_move_logs_history(self):
        # Create task
        item = Item.objects.create(
            board=self.board,
            column=self.column1,
            title="Ko'chiriladigan Vazifa",
            organization=self.org,
            branch=self.branch
        )
        
        url = reverse('item-move', kwargs={'pk': item.id})
        data = {
            "column_id": self.column2.id
        }
        
        response = self.client.post(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check if TaskHistory logs movement
        history = TaskHistory.objects.filter(item=item, action="moved")
        self.assertEqual(history.count(), 1)
        
        record = history.first()
        self.assertIn("Vazifa ko'chirildi", record.details)
        self.assertIn("To Do", record.details)
        self.assertIn("In Progress", record.details)

    def test_comment_addition_logs_history(self):
        # Create task
        item = Item.objects.create(
            board=self.board,
            column=self.column1,
            title="Sharh Vazifasi",
            organization=self.org,
            branch=self.branch
        )
        
        url = reverse('comment-list')
        data = {
            "item": item.id,
            "text": "Bu juda muhim vazifa!"
        }
        
        response = self.client.post(f"{url}?org_id={self.org.id}", data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Check if comment_added action is logged
        history = TaskHistory.objects.filter(item=item, action="comment_added")
        self.assertEqual(history.count(), 1)
        self.assertIn("Yangi sharh qo'shildi", history.first().details)
        self.assertIn("Bu juda muhim vazifa!", history.first().details)

    def test_history_api_endpoints(self):
        # Create task and add some history
        item = Item.objects.create(
            board=self.board,
            column=self.column1,
            title="Tarix Vazifasi",
            organization=self.org,
            branch=self.branch
        )
        
        TaskHistory.objects.create(
            item=item,
            user=self.user,
            action="created",
            details="Test yaratilish tarixi",
            organization=self.org,
            branch=self.branch
        )
        
        # Test 1: Nested endpoint /api/v1/tasks/items/{id}/history/
        url1 = reverse('item-history', kwargs={'pk': item.id})
        response1 = self.client.get(f"{url1}?org_id={self.org.id}")
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        
        results1 = response1.data.get('results') if isinstance(response1.data, dict) else response1.data
        self.assertEqual(len(results1), 1)
        self.assertEqual(results1[0]['details'], "Test yaratilish tarixi")
        self.assertEqual(results1[0]['user_name'], "Ali Valiyev")
        
        # Test 2: General endpoint /api/v1/tasks/history/?item_id={id}
        url2 = reverse('taskhistory-list')
        response2 = self.client.get(f"{url2}?item_id={item.id}&org_id={self.org.id}")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        
        results2 = response2.data.get('results') if isinstance(response2.data, dict) else response2.data
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]['details'], "Test yaratilish tarixi")

    def test_task_assignment_notifications(self):
        """
        Verify that notify_task_assignment is triggered when a task is created or updated.
        """
        # Set user telegram_chat_id
        self.user.telegram_chat_id = "123456789"
        self.user.save()

        # Mock send_telegram_message using unittest.mock
        from unittest.mock import patch
        with patch('academics.telegram_bot.send_telegram_message') as mock_send:
            # 1. Create a task with assigned user
            item = Item.objects.create(
                board=self.board,
                column=self.column1,
                title="Sarlavha",
                assigned_to=self.user,
                organization=self.org,
                branch=self.branch
            )
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_count, 1)

            mock_send.reset_mock()

            # 2. Update the task assignment (same user -> should NOT send again)
            item.title = "Yangilangan Sarlavha"
            item.save()
            self.assertFalse(mock_send.called)

            # 3. Change assignment (None -> user)
            item.assigned_to = None
            item.save()
            mock_send.reset_mock()

            item.assigned_to = self.user
            item.save()
            self.assertTrue(mock_send.called)
            self.assertEqual(mock_send.call_count, 1)
