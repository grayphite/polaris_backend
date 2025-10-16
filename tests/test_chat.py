"""
Unit tests for Chat feature

Tests models, services, and routes for chat management
including cascade behavior with projects.
"""

import unittest
import os
import json
from datetime import datetime, UTC
from unittest.mock import Mock, patch, MagicMock

# Set test environment
os.environ['TESTING'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from flask import Flask
from src.extensions import db
from src.models.chat import Chat
from src.models.project import Project
from src.models.user import User
from src.services.chat_service import ChatService, chat_service
from src.services.project_service import project_service
from src.services.auth_service import auth_service
from src.routes.chat import chat_bp


class TestChatModel(unittest.TestCase):
    """Tests for Chat model"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test Flask app and database"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        
        db.init_app(cls.app)
        
        with cls.app.app_context():
            db.create_all()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests"""
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
    
    def setUp(self):
        """Set up each test"""
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Create test user
        self.test_user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed',
            first_name='Test',
            last_name='User'
        )
        db.session.add(self.test_user)
        db.session.commit()
        
        # Create test project
        self.test_project = Project(
            name="Test Project",
            description="Test Description",
            created_by=self.test_user.id
        )
        db.session.add(self.test_project)
        db.session.commit()
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Chat.query.delete()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_chat(self):
        """Test creating a chat"""
        chat = Chat(
            name="Test Chat",
            description="Test Description",
            project_id=self.test_project.id,
            created_by=self.test_user.id
        )
        
        db.session.add(chat)
        db.session.commit()
        
        self.assertIsNotNone(chat.id)
        self.assertEqual(chat.name, "Test Chat")
        self.assertEqual(chat.project_id, self.test_project.id)
        self.assertFalse(chat.is_deleted)
        self.assertIsNotNone(chat.created_at)
    
    def test_chat_to_dict(self):
        """Test chat to_dict method"""
        chat = Chat(
            name="Test Chat",
            description="Test Description",
            project_id=self.test_project.id,
            created_by=self.test_user.id
        )
        
        db.session.add(chat)
        db.session.commit()
        
        chat_dict = chat.to_dict()
        
        self.assertIn('id', chat_dict)
        self.assertIn('name', chat_dict)
        self.assertIn('project_id', chat_dict)
        self.assertIn('created_at', chat_dict)
        self.assertEqual(chat_dict['name'], "Test Chat")
        self.assertEqual(chat_dict['project_id'], self.test_project.id)
    
    def test_chat_soft_delete(self):
        """Test soft delete functionality"""
        chat = Chat(
            name="Test Chat",
            project_id=self.test_project.id,
            created_by=self.test_user.id
        )
        
        db.session.add(chat)
        db.session.commit()
        
        # Soft delete
        chat.is_deleted = True
        chat.deleted_at = datetime.now(UTC)
        chat.deleted_by = self.test_user.id
        db.session.commit()
        
        self.assertTrue(chat.is_deleted)
        self.assertIsNotNone(chat.deleted_at)
        self.assertEqual(chat.deleted_by, self.test_user.id)
    
    def test_chat_project_relationship(self):
        """Test chat-project relationship"""
        chat = Chat(
            name="Test Chat",
            project_id=self.test_project.id,
            created_by=self.test_user.id
        )
        
        db.session.add(chat)
        db.session.commit()
        
        # Test relationship
        self.assertEqual(chat.project.id, self.test_project.id)
        self.assertEqual(chat.project.name, "Test Project")


class TestChatService(unittest.TestCase):
    """Tests for ChatService"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        
        db.init_app(cls.app)
        
        with cls.app.app_context():
            db.create_all()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests"""
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
    
    def setUp(self):
        """Set up each test"""
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.service = ChatService()
        
        # Create test user
        self.test_user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed',
            first_name='Test',
            last_name='User'
        )
        db.session.add(self.test_user)
        db.session.commit()
        
        # Create test project
        self.test_project = Project(
            name="Test Project",
            description="Test Description",
            created_by=self.test_user.id
        )
        db.session.add(self.test_project)
        db.session.commit()
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Chat.query.delete()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_chat_success(self):
        """Test successful chat creation"""
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id,
            description="Test Description"
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.chat)
        self.assertEqual(result.chat['name'], "Test Chat")
        self.assertEqual(result.chat['project_id'], self.test_project.id)
    
    def test_create_chat_empty_name(self):
        """Test chat creation with empty name"""
        result = self.service.create_chat(
            name="",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        self.assertFalse(result.success)
        self.assertIn("required", result.error.lower())
    
    def test_create_chat_invalid_project(self):
        """Test chat creation with invalid project"""
        result = self.service.create_chat(
            name="Test Chat",
            project_id=99999,
            user_id=self.test_user.id
        )
        
        self.assertFalse(result.success)
        self.assertIn("not found", result.error.lower())
    
    def test_create_chat_touches_project(self):
        """Test that creating chat updates project's updated_at"""
        # Get original project timestamp
        original_updated_at = self.test_project.updated_at
        
        # Create chat
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        # Refresh project
        db.session.refresh(self.test_project)
        
        # Verify project was touched
        self.assertTrue(result.success)
        self.assertGreater(self.test_project.updated_at, original_updated_at)
    
    def test_get_chat_by_id(self):
        """Test fetching chat by ID"""
        # Create chat
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        chat_id = result.chat['id']
        
        # Fetch chat
        chat = self.service.get_chat_by_id(chat_id, self.test_user.id)
        
        self.assertIsNotNone(chat)
        self.assertEqual(chat['id'], chat_id)
    
    def test_update_chat(self):
        """Test updating a chat"""
        # Create chat
        result = self.service.create_chat(
            name="Original Name",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        chat_id = result.chat['id']
        
        # Update chat
        update_result = self.service.update_chat(
            chat_id=chat_id,
            user_id=self.test_user.id,
            data={'name': 'Updated Name'}
        )
        
        self.assertTrue(update_result.success)
        self.assertEqual(update_result.chat['name'], 'Updated Name')
    
    def test_update_chat_touches_project(self):
        """Test that updating chat updates project's updated_at"""
        # Create chat
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        chat_id = result.chat['id']
        
        # Refresh and get original timestamp
        db.session.refresh(self.test_project)
        original_updated_at = self.test_project.updated_at
        
        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)
        
        # Update chat
        update_result = self.service.update_chat(
            chat_id=chat_id,
            user_id=self.test_user.id,
            data={'name': 'Updated Name'}
        )
        
        # Refresh project
        db.session.refresh(self.test_project)
        
        # Verify project was touched
        self.assertTrue(update_result.success)
        self.assertGreater(self.test_project.updated_at, original_updated_at)
    
    def test_soft_delete_chat(self):
        """Test soft deleting a chat"""
        # Create chat
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        chat_id = result.chat['id']
        
        # Delete chat
        delete_result = self.service.delete_chat(chat_id, self.test_user.id)
        
        self.assertTrue(delete_result.success)
        
        # Verify it's soft-deleted
        chat = self.service.get_chat_by_id(
            chat_id, 
            self.test_user.id, 
            include_deleted=True
        )
        self.assertTrue(chat['is_deleted'])
    
    def test_restore_chat(self):
        """Test restoring a soft-deleted chat"""
        # Create and delete chat
        result = self.service.create_chat(
            name="Test Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        chat_id = result.chat['id']
        
        self.service.delete_chat(chat_id, self.test_user.id)
        
        # Restore chat
        restore_result = self.service.restore_chat(chat_id, self.test_user.id)
        
        self.assertTrue(restore_result.success)
        self.assertFalse(restore_result.chat['is_deleted'])
    
    def test_list_chats(self):
        """Test listing chats with pagination"""
        # Create multiple chats
        for i in range(5):
            self.service.create_chat(
                name=f"Chat {i}",
                project_id=self.test_project.id,
                user_id=self.test_user.id
            )
        
        # List chats
        result = self.service.list_chats(
            user_id=self.test_user.id,
            page=1,
            per_page=10
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['chats']), 5)
        self.assertEqual(result['pagination']['total'], 5)
    
    def test_list_chats_by_project(self):
        """Test listing chats for specific project"""
        # Create another project
        project2 = Project(
            name="Project 2",
            created_by=self.test_user.id
        )
        db.session.add(project2)
        db.session.commit()
        
        # Create chats in both projects
        self.service.create_chat("Chat 1", self.test_project.id, self.test_user.id)
        self.service.create_chat("Chat 2", self.test_project.id, self.test_user.id)
        self.service.create_chat("Chat 3", project2.id, self.test_user.id)
        
        # List chats for first project only
        result = self.service.list_chats_by_project(
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['chats']), 2)
    
    def test_list_chats_with_search(self):
        """Test listing chats with search query"""
        # Create chats
        self.service.create_chat(
            name="Alpha Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        self.service.create_chat(
            name="Beta Chat",
            project_id=self.test_project.id,
            user_id=self.test_user.id
        )
        
        # Search for "Alpha"
        result = self.service.list_chats(
            user_id=self.test_user.id,
            search="Alpha"
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['chats']), 1)
        self.assertIn('Alpha', result['chats'][0]['name'])
    
    def test_get_statistics(self):
        """Test getting chat statistics"""
        # Create chats
        self.service.create_chat("Chat 1", self.test_project.id, self.test_user.id)
        result = self.service.create_chat("Chat 2", self.test_project.id, self.test_user.id)
        
        # Delete one
        self.service.delete_chat(result.chat['id'], self.test_user.id)
        
        # Get statistics
        stats = self.service.get_chat_statistics(self.test_user.id)
        
        self.assertEqual(stats['total_chats'], 2)
        self.assertEqual(stats['active_chats'], 1)
        self.assertEqual(stats['deleted_chats'], 1)


class TestChatCascadeBehavior(unittest.TestCase):
    """Tests for cascade behavior between projects and chats"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        
        db.init_app(cls.app)
        
        with cls.app.app_context():
            db.create_all()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests"""
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
    
    def setUp(self):
        """Set up each test"""
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Create test user
        self.test_user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed',
            first_name='Test',
            last_name='User'
        )
        db.session.add(self.test_user)
        db.session.commit()
        
        # Create test project
        result = project_service.create_project(
            name="Test Project",
            user_id=self.test_user.id
        )
        self.test_project_id = result.project['id']
        
        # Create test chats
        chat_service.create_chat("Chat 1", self.test_project_id, self.test_user.id)
        chat_service.create_chat("Chat 2", self.test_project_id, self.test_user.id)
        chat_service.create_chat("Chat 3", self.test_project_id, self.test_user.id)
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Chat.query.delete()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_cascade_delete_chats_when_project_deleted(self):
        """Test that deleting project cascades to chats"""
        # Verify chats exist
        chats_before = chat_service.list_chats(user_id=self.test_user.id)
        self.assertEqual(chats_before['pagination']['total'], 3)
        
        # Delete project
        project_service.delete_project(self.test_project_id, self.test_user.id)
        
        # Verify chats are also soft-deleted
        chats_active = chat_service.list_chats(
            user_id=self.test_user.id,
            include_deleted=False
        )
        self.assertEqual(chats_active['pagination']['total'], 0)
        
        # Verify chats still exist but are deleted
        chats_all = chat_service.list_chats(
            user_id=self.test_user.id,
            include_deleted=True
        )
        self.assertEqual(chats_all['pagination']['total'], 3)
        for chat in chats_all['chats']:
            self.assertTrue(chat['is_deleted'])
    
    def test_cascade_restore_chats_when_project_restored(self):
        """Test that restoring project cascades to chats"""
        # Delete project (which cascades to chats)
        project_service.delete_project(self.test_project_id, self.test_user.id)
        
        # Verify chats are deleted
        chats_active = chat_service.list_chats(user_id=self.test_user.id)
        self.assertEqual(chats_active['pagination']['total'], 0)
        
        # Restore project
        project_service.restore_project(self.test_project_id, self.test_user.id)
        
        # Verify chats are also restored
        chats_restored = chat_service.list_chats(user_id=self.test_user.id)
        self.assertEqual(chats_restored['pagination']['total'], 3)
        for chat in chats_restored['chats']:
            self.assertFalse(chat['is_deleted'])


class TestChatRoutes(unittest.TestCase):
    """Tests for Chat routes"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-secret-key'
        
        db.init_app(cls.app)
        cls.app.register_blueprint(chat_bp, url_prefix='/api')
        
        with cls.app.app_context():
            db.create_all()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests"""
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
    
    def setUp(self):
        """Set up each test"""
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        
        # Create test user
        self.test_user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed',
            first_name='Test',
            last_name='User'
        )
        db.session.add(self.test_user)
        db.session.commit()
        
        # Create test project
        self.test_project = Project(
            name="Test Project",
            created_by=self.test_user.id
        )
        db.session.add(self.test_project)
        db.session.commit()
        
        # Generate auth token
        self.token, _ = auth_service._generate_token(self.test_user)
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Chat.query.delete()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_chat_endpoint(self):
        """Test POST /api/chats"""
        response = self.client.post(
            '/api/chats',
            headers=self.headers,
            data=json.dumps({
                'name': 'Test Chat',
                'description': 'Test Description',
                'project_id': self.test_project.id
            })
        )
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'Test Chat')
        self.assertEqual(data['project_id'], self.test_project.id)
    
    def test_create_chat_missing_name(self):
        """Test POST /api/chats without name"""
        response = self.client.post(
            '/api/chats',
            headers=self.headers,
            data=json.dumps({
                'project_id': self.test_project.id
            })
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_create_chat_missing_project_id(self):
        """Test POST /api/chats without project_id"""
        response = self.client.post(
            '/api/chats',
            headers=self.headers,
            data=json.dumps({
                'name': 'Test Chat'
            })
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_get_chats_endpoint(self):
        """Test GET /api/chats"""
        # Create test chat
        chat_service.create_chat("Test Chat", self.test_project.id, self.test_user.id)
        
        response = self.client.get(
            '/api/chats',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('chats', data)
        self.assertIn('pagination', data)
    
    def test_get_chat_by_id_endpoint(self):
        """Test GET /api/chats/<id>"""
        # Create chat
        result = chat_service.create_chat("Test Chat", self.test_project.id, self.test_user.id)
        chat_id = result.chat['id']
        
        response = self.client.get(
            f'/api/chats/{chat_id}',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['id'], chat_id)
    
    def test_get_project_chats_endpoint(self):
        """Test GET /api/projects/<project_id>/chats"""
        # Create chats
        chat_service.create_chat("Chat 1", self.test_project.id, self.test_user.id)
        chat_service.create_chat("Chat 2", self.test_project.id, self.test_user.id)
        
        response = self.client.get(
            f'/api/projects/{self.test_project.id}/chats',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data['chats']), 2)
    
    def test_update_chat_endpoint(self):
        """Test PUT /api/chats/<id>"""
        # Create chat
        result = chat_service.create_chat("Original Name", self.test_project.id, self.test_user.id)
        chat_id = result.chat['id']
        
        response = self.client.put(
            f'/api/chats/{chat_id}',
            headers=self.headers,
            data=json.dumps({
                'name': 'Updated Name'
            })
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'Updated Name')
    
    def test_delete_chat_endpoint(self):
        """Test DELETE /api/chats/<id>"""
        # Create chat
        result = chat_service.create_chat("Test Chat", self.test_project.id, self.test_user.id)
        chat_id = result.chat['id']
        
        response = self.client.delete(
            f'/api/chats/{chat_id}',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify chat is soft-deleted
        chat = chat_service.get_chat_by_id(
            chat_id, 
            self.test_user.id, 
            include_deleted=True
        )
        self.assertTrue(chat['is_deleted'])
    
    def test_restore_chat_endpoint(self):
        """Test POST /api/chats/<id>/restore"""
        # Create and delete chat
        result = chat_service.create_chat("Test Chat", self.test_project.id, self.test_user.id)
        chat_id = result.chat['id']
        chat_service.delete_chat(chat_id, self.test_user.id)
        
        # Restore
        response = self.client.post(
            f'/api/chats/{chat_id}/restore',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['is_deleted'])
    
    def test_get_stats_endpoint(self):
        """Test GET /api/chats/stats"""
        # Create some chats
        chat_service.create_chat("Chat 1", self.test_project.id, self.test_user.id)
        chat_service.create_chat("Chat 2", self.test_project.id, self.test_user.id)
        
        response = self.client.get(
            '/api/chats/stats',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('total_chats', data)
        self.assertIn('active_chats', data)
    
    def test_unauthorized_access(self):
        """Test access without authentication"""
        response = self.client.get('/api/chats')
        self.assertEqual(response.status_code, 401)
    
    def test_health_check_endpoint(self):
        """Test GET /api/chats/health"""
        response = self.client.get('/api/chats/health')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('status', data)


def run_tests():
    """Run all chat tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestChatModel))
    suite.addTests(loader.loadTestsFromTestCase(TestChatService))
    suite.addTests(loader.loadTestsFromTestCase(TestChatCascadeBehavior))
    suite.addTests(loader.loadTestsFromTestCase(TestChatRoutes))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)


