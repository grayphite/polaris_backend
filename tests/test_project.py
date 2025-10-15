"""
Unit tests for Project feature

Tests models, services, and routes for project management.
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
from src.models.project import Project
from src.models.user import User
from src.services.project_service import ProjectService, project_service
from src.services.auth_service import auth_service
from src.routes.project import project_bp


class TestProjectModel(unittest.TestCase):
    """Tests for Project model"""
    
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
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_project(self):
        """Test creating a project"""
        project = Project(
            name="Test Project",
            description="Test Description",
            created_by=self.test_user.id
        )
        
        db.session.add(project)
        db.session.commit()
        
        self.assertIsNotNone(project.id)
        self.assertEqual(project.name, "Test Project")
        self.assertFalse(project.is_deleted)
        self.assertIsNotNone(project.created_at)
    
    def test_project_to_dict(self):
        """Test project to_dict method"""
        project = Project(
            name="Test Project",
            description="Test Description",
            created_by=self.test_user.id
        )
        
        db.session.add(project)
        db.session.commit()
        
        project_dict = project.to_dict()
        
        self.assertIn('id', project_dict)
        self.assertIn('name', project_dict)
        self.assertIn('created_at', project_dict)
        self.assertEqual(project_dict['name'], "Test Project")
    
    def test_project_soft_delete(self):
        """Test soft delete functionality"""
        project = Project(
            name="Test Project",
            created_by=self.test_user.id
        )
        
        db.session.add(project)
        db.session.commit()
        
        # Soft delete
        project.is_deleted = True
        project.deleted_at = datetime.now(UTC)
        project.deleted_by = self.test_user.id
        db.session.commit()
        
        self.assertTrue(project.is_deleted)
        self.assertIsNotNone(project.deleted_at)
        self.assertEqual(project.deleted_by, self.test_user.id)


class TestProjectService(unittest.TestCase):
    """Tests for ProjectService"""
    
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
        self.service = ProjectService()
        
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
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_project_success(self):
        """Test successful project creation"""
        result = self.service.create_project(
            name="Test Project",
            user_id=self.test_user.id,
            description="Test Description"
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.project)
        self.assertEqual(result.project['name'], "Test Project")
    
    def test_create_project_empty_name(self):
        """Test project creation with empty name"""
        result = self.service.create_project(
            name="",
            user_id=self.test_user.id
        )
        
        self.assertFalse(result.success)
        self.assertIn("required", result.error.lower())
    
    def test_get_project_by_id(self):
        """Test fetching project by ID"""
        # Create project
        result = self.service.create_project(
            name="Test Project",
            user_id=self.test_user.id
        )
        
        project_id = result.project['id']
        
        # Fetch project
        project = self.service.get_project_by_id(project_id, self.test_user.id)
        
        self.assertIsNotNone(project)
        self.assertEqual(project['id'], project_id)
    
    def test_update_project(self):
        """Test updating a project"""
        # Create project
        result = self.service.create_project(
            name="Original Name",
            user_id=self.test_user.id
        )
        
        project_id = result.project['id']
        
        # Update project
        update_result = self.service.update_project(
            project_id=project_id,
            user_id=self.test_user.id,
            data={'name': 'Updated Name'}
        )
        
        self.assertTrue(update_result.success)
        self.assertEqual(update_result.project['name'], 'Updated Name')
    
    def test_soft_delete_project(self):
        """Test soft deleting a project"""
        # Create project
        result = self.service.create_project(
            name="Test Project",
            user_id=self.test_user.id
        )
        
        project_id = result.project['id']
        
        # Delete project
        delete_result = self.service.delete_project(project_id, self.test_user.id)
        
        self.assertTrue(delete_result.success)
        
        # Verify it's soft-deleted
        project = self.service.get_project_by_id(
            project_id, 
            self.test_user.id, 
            include_deleted=True
        )
        self.assertTrue(project['is_deleted'])
    
    def test_restore_project(self):
        """Test restoring a soft-deleted project"""
        # Create and delete project
        result = self.service.create_project(
            name="Test Project",
            user_id=self.test_user.id
        )
        project_id = result.project['id']
        
        self.service.delete_project(project_id, self.test_user.id)
        
        # Restore project
        restore_result = self.service.restore_project(project_id, self.test_user.id)
        
        self.assertTrue(restore_result.success)
        self.assertFalse(restore_result.project['is_deleted'])
    
    def test_list_projects(self):
        """Test listing projects with pagination"""
        # Create multiple projects
        for i in range(5):
            self.service.create_project(
                name=f"Project {i}",
                user_id=self.test_user.id
            )
        
        # List projects
        result = self.service.list_projects(
            user_id=self.test_user.id,
            page=1,
            per_page=10
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['projects']), 5)
        self.assertEqual(result['pagination']['total'], 5)
    
    def test_list_projects_with_search(self):
        """Test listing projects with search query"""
        # Create projects
        self.service.create_project(
            name="Alpha Project",
            user_id=self.test_user.id
        )
        self.service.create_project(
            name="Beta Project",
            user_id=self.test_user.id
        )
        
        # Search for "Alpha"
        result = self.service.list_projects(
            user_id=self.test_user.id,
            search="Alpha"
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(len(result['projects']), 1)
        self.assertIn('Alpha', result['projects'][0]['name'])
    
    def test_get_statistics(self):
        """Test getting project statistics"""
        # Create projects
        self.service.create_project("Project 1", self.test_user.id)
        result = self.service.create_project("Project 2", self.test_user.id)
        
        # Delete one
        self.service.delete_project(result.project['id'], self.test_user.id)
        
        # Get statistics
        stats = self.service.get_project_statistics(self.test_user.id)
        
        self.assertEqual(stats['total_projects'], 2)
        self.assertEqual(stats['active_projects'], 1)
        self.assertEqual(stats['deleted_projects'], 1)


class TestProjectRoutes(unittest.TestCase):
    """Tests for Project routes"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test Flask app"""
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-secret-key'
        
        db.init_app(cls.app)
        cls.app.register_blueprint(project_bp, url_prefix='/api')
        
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
        
        # Generate auth token
        self.token, _ = auth_service._generate_token(self.test_user)
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def tearDown(self):
        """Clean up after each test"""
        db.session.rollback()
        Project.query.delete()
        User.query.delete()
        db.session.commit()
        self.app_context.pop()
    
    def test_create_project_endpoint(self):
        """Test POST /api/projects"""
        response = self.client.post(
            '/api/projects',
            headers=self.headers,
            data=json.dumps({
                'name': 'Test Project',
                'description': 'Test Description'
            })
        )
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'Test Project')
    
    def test_create_project_missing_name(self):
        """Test POST /api/projects without project_name"""
        response = self.client.post(
            '/api/projects',
            headers=self.headers,
            data=json.dumps({})
        )
        
        self.assertEqual(response.status_code, 400)
    
    def test_get_projects_endpoint(self):
        """Test GET /api/projects"""
        # Create test project
        project_service.create_project("Test Project", self.test_user.id)
        
        response = self.client.get(
            '/api/projects',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('projects', data)
        self.assertIn('pagination', data)
    
    def test_get_project_by_id_endpoint(self):
        """Test GET /api/projects/<id>"""
        # Create project
        result = project_service.create_project("Test Project", self.test_user.id)
        project_id = result.project['id']
        
        response = self.client.get(
            f'/api/projects/{project_id}',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['id'], project_id)
    
    def test_update_project_endpoint(self):
        """Test PUT /api/projects/<id>"""
        # Create project
        result = project_service.create_project("Original Name", self.test_user.id)
        project_id = result.project['id']
        
        response = self.client.put(
            f'/api/projects/{project_id}',
            headers=self.headers,
            data=json.dumps({
                'name': 'Updated Name'
            })
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['name'], 'Updated Name')
    
    def test_delete_project_endpoint(self):
        """Test DELETE /api/projects/<id>"""
        # Create project
        result = project_service.create_project("Test Project", self.test_user.id)
        project_id = result.project['id']
        
        response = self.client.delete(
            f'/api/projects/{project_id}',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify project is soft-deleted
        project = project_service.get_project_by_id(
            project_id, 
            self.test_user.id, 
            include_deleted=True
        )
        self.assertTrue(project['is_deleted'])
    
    def test_restore_project_endpoint(self):
        """Test POST /api/projects/<id>/restore"""
        # Create and delete project
        result = project_service.create_project("Test Project", self.test_user.id)
        project_id = result.project['id']
        project_service.delete_project(project_id, self.test_user.id)
        
        # Restore
        response = self.client.post(
            f'/api/projects/{project_id}/restore',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data['is_deleted'])
    
    def test_get_stats_endpoint(self):
        """Test GET /api/projects/stats"""
        # Create some projects
        project_service.create_project("Project 1", self.test_user.id)
        project_service.create_project("Project 2", self.test_user.id)
        
        response = self.client.get(
            '/api/projects/stats',
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('total_projects', data)
        self.assertIn('active_projects', data)
    
    def test_unauthorized_access(self):
        """Test access without authentication"""
        response = self.client.get('/api/projects')
        self.assertEqual(response.status_code, 401)
    
    def test_health_check_endpoint(self):
        """Test GET /api/projects/health"""
        response = self.client.get('/api/projects/health')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('status', data)


def run_tests():
    """Run all project tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestProjectModel))
    suite.addTests(loader.loadTestsFromTestCase(TestProjectService))
    suite.addTests(loader.loadTestsFromTestCase(TestProjectRoutes))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)

