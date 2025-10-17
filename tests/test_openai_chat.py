"""
Test suite for OpenAI Chat functionality

Tests CRUD operations, message sending, and OpenAI integration
for the AI chat system.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.models import User, Project, Chat, AIChat, AIStats
from src.services.openai_chat_service import OpenAIChatService, OpenAIResponse
from src.extensions import db


@pytest.fixture
def app():
    """Create test application"""
    from src.main import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def auth_headers(client):
    """Create authenticated user and return auth headers"""
    # Create test user
    user = User(
        username='testuser',
        email='test@example.com',
        first_name='Test',
        last_name='User'
    )
    user.set_password('testpassword')
    
    db.session.add(user)
    db.session.commit()
    
    # Login to get token
    login_response = client.post('/api/users/login', json={
        'email': 'test@example.com',
        'senha': 'testpassword'
    })
    
    token = login_response.json['token']
    
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }


@pytest.fixture
def test_project(auth_headers):
    """Create test project"""
    project = Project(
        name='Test Project',
        description='Test project description',
        created_by=1,  # Assuming user ID 1
        is_deleted=False
    )
    db.session.add(project)
    db.session.commit()
    return project


@pytest.fixture
def test_chat(test_project):
    """Create test chat"""
    chat = Chat(
        name='Test Chat',
        description='Test chat description',
        project_id=test_project.id,
        created_by=1,  # Assuming user ID 1
        is_deleted=False
    )
    db.session.add(chat)
    db.session.commit()
    return chat


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response"""
    return OpenAIResponse(
        success=True,
        content="This is a test AI response",
        usage={
            'total_tokens': 50,
            'prompt_tokens': 20,
            'completion_tokens': 30
        },
        model='gpt-4.1',
        request_id='test-request-id',
        response_time_ms=1500
    )


class TestAIChatModels:
    """Test AI chat models"""
    
    def test_ai_chat_creation(self, app, test_chat):
        """Test AIChat model creation"""
        with app.app_context():
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="What is the capital of France?",
                ai_answer="The capital of France is Paris.",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI",
                context_metadata={'test': 'data'}
            )
            
            db.session.add(ai_chat)
            db.session.commit()
            
            assert ai_chat.id is not None
            assert ai_chat.chat_id == test_chat.id
            assert ai_chat.user_id == 1
            assert ai_chat.user_question == "What is the capital of France?"
            assert ai_chat.ai_answer == "The capital of France is Paris."
            assert ai_chat.ai_model == "gpt-4.1"
            assert ai_chat.ai_model_provider == "OpenAI"
            assert ai_chat.context_metadata == {'test': 'data'}
            assert ai_chat.is_deleted is False
    
    def test_ai_stats_creation(self, app, test_chat):
        """Test AIStats model creation"""
        with app.app_context():
            # Create AI chat first
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="Test question",
                ai_answer="Test answer",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            db.session.add(ai_chat)
            db.session.flush()
            
            # Create AI stats
            ai_stats = AIStats(
                ai_chat_id=ai_chat.id,
                tokens_used=100,
                prompt_tokens=40,
                completion_tokens=60,
                response_time_ms=2000,
                cost_usd=0.001,
                api_version='v1',
                request_id='test-request-id'
            )
            
            db.session.add(ai_stats)
            db.session.commit()
            
            assert ai_stats.id is not None
            assert ai_stats.ai_chat_id == ai_chat.id
            assert ai_stats.tokens_used == 100
            assert ai_stats.prompt_tokens == 40
            assert ai_stats.completion_tokens == 60
            assert ai_stats.response_time_ms == 2000
            assert float(ai_stats.cost_usd) == 0.001
    
    def test_ai_chat_to_dict(self, app, test_chat):
        """Test AIChat to_dict method"""
        with app.app_context():
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="Test question",
                ai_answer="Test answer",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            
            ai_dict = ai_chat.to_dict()
            
            assert isinstance(ai_dict, dict)
            assert 'id' in ai_dict
            assert 'chat_id' in ai_dict
            assert 'user_id' in ai_dict
            assert 'user_question' in ai_dict
            assert 'ai_answer' in ai_dict
            assert 'ai_model' in ai_dict
            assert 'ai_model_provider' in ai_dict
            assert 'created_at' in ai_dict


class TestOpenAIChatService:
    """Test OpenAI Chat Service"""
    
    @patch('src.services.openai_chat_service.openai')
    def test_create_ai_chat_success(self, mock_openai, app, test_chat, mock_openai_response):
        """Test successful AI chat creation"""
        with app.app_context():
            # Mock OpenAI response
            mock_openai.ChatCompletion.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Test AI response"))],
                usage=MagicMock(to_dict=lambda: {'total_tokens': 50, 'prompt_tokens': 20, 'completion_tokens': 30}),
                model='gpt-4.1',
                id='test-request-id'
            )
            
            service = OpenAIChatService()
            service.openai_client = mock_openai
            
            result = service.create_ai_chat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="What is AI?",
                ai_model="gpt-4.1"
            )
            
            assert result.success is True
            assert result.ai_chat is not None
            assert result.ai_chat['user_question'] == "What is AI?"
            assert result.ai_chat['ai_answer'] == "Test AI response"
            assert result.ai_chat['ai_model'] == "gpt-4.1"
            assert result.ai_chat['ai_model_provider'] == "OpenAI"
            
            # Verify AI chat was saved to database
            ai_chat = AIChat.query.filter_by(chat_id=test_chat.id).first()
            assert ai_chat is not None
            assert ai_chat.user_question == "What is AI?"
            assert ai_chat.ai_answer == "Test AI response"
            
            # Verify AI stats were created
            ai_stats = AIStats.query.filter_by(ai_chat_id=ai_chat.id).first()
            assert ai_stats is not None
            assert ai_stats.tokens_used == 50
    
    def test_create_ai_chat_invalid_question(self, app, test_chat):
        """Test AI chat creation with invalid question"""
        with app.app_context():
            service = OpenAIChatService()
            
            result = service.create_ai_chat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="",  # Empty question
                ai_model="gpt-4.1"
            )
            
            assert result.success is False
            assert "required" in result.error.lower()
    
    def test_create_ai_chat_access_denied(self, app, test_chat):
        """Test AI chat creation with access denied"""
        with app.app_context():
            service = OpenAIChatService()
            
            result = service.create_ai_chat(
                chat_id=test_chat.id,
                user_id=999,  # Different user ID
                user_question="What is AI?",
                ai_model="gpt-4.1"
            )
            
            assert result.success is False
            assert "access denied" in result.error.lower()
    
    def test_get_ai_chat_by_id(self, app, test_chat):
        """Test getting AI chat by ID"""
        with app.app_context():
            # Create AI chat
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="Test question",
                ai_answer="Test answer",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            db.session.add(ai_chat)
            db.session.commit()
            
            service = OpenAIChatService()
            result = service.get_ai_chat_by_id(ai_chat.id, 1)
            
            assert result is not None
            assert result['id'] == ai_chat.id
            assert result['user_question'] == "Test question"
            assert result['ai_answer'] == "Test answer"
    
    def test_list_ai_chats(self, app, test_chat):
        """Test listing AI chats"""
        with app.app_context():
            # Create multiple AI chats
            for i in range(3):
                ai_chat = AIChat(
                    chat_id=test_chat.id,
                    user_id=1,
                    user_question=f"Question {i}",
                    ai_answer=f"Answer {i}",
                    ai_model="gpt-4.1",
                    ai_model_provider="OpenAI"
                )
                db.session.add(ai_chat)
            db.session.commit()
            
            service = OpenAIChatService()
            result = service.list_ai_chats(chat_id=test_chat.id, user_id=1)
            
            assert result['success'] is True
            assert len(result['ai_chats']) == 3
            assert result['pagination']['total'] == 3
    
    def test_update_ai_chat(self, app, test_chat):
        """Test updating AI chat"""
        with app.app_context():
            # Create AI chat
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="Original question",
                ai_answer="Original answer",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            db.session.add(ai_chat)
            db.session.commit()
            
            service = OpenAIChatService()
            result = service.update_ai_chat(
                ai_chat_id=ai_chat.id,
                user_id=1,
                data={'user_question': 'Updated question'}
            )
            
            assert result.success is True
            assert result.ai_chat['user_question'] == 'Updated question'
    
    def test_delete_ai_chat(self, app, test_chat):
        """Test soft deleting AI chat"""
        with app.app_context():
            # Create AI chat
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question="Test question",
                ai_answer="Test answer",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            db.session.add(ai_chat)
            db.session.commit()
            
            service = OpenAIChatService()
            result = service.delete_ai_chat(ai_chat.id, 1)
            
            assert result.success is True
            
            # Verify soft delete
            deleted_chat = AIChat.query.filter_by(id=ai_chat.id).first()
            assert deleted_chat.is_deleted is True
            assert deleted_chat.deleted_at is not None


class TestOpenAIChatRoutes:
    """Test OpenAI Chat Routes"""
    
    def test_list_ai_chats_endpoint(self, client, auth_headers, test_chat):
        """Test listing AI chats endpoint"""
        response = client.get(
            f'/api/chats/{test_chat.id}/ai-chats',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json
        assert 'ai_chats' in data
        assert 'pagination' in data
    
    def test_create_ai_chat_endpoint(self, client, auth_headers, test_chat):
        """Test creating AI chat endpoint"""
        with patch('src.services.openai_chat_service.openai') as mock_openai:
            # Mock OpenAI response
            mock_openai.ChatCompletion.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Test AI response"))],
                usage=MagicMock(to_dict=lambda: {'total_tokens': 50}),
                model='gpt-4.1',
                id='test-request-id'
            )
            
            response = client.post(
                f'/api/chats/{test_chat.id}/ai-chats',
                headers=auth_headers,
                json={
                    'user_question': 'What is artificial intelligence?',
                    'ai_model': 'gpt-4.1'
                }
            )
            
            assert response.status_code == 201
            data = response.json
            assert data['user_question'] == 'What is artificial intelligence?'
            assert data['ai_answer'] == 'Test AI response'
            assert data['ai_model'] == 'gpt-4.1'
            assert data['ai_model_provider'] == 'OpenAI'
    
    def test_send_message_endpoint(self, client, auth_headers, test_chat):
        """Test send message endpoint"""
        with patch('src.services.openai_chat_service.openai') as mock_openai:
            # Mock OpenAI response
            mock_openai.ChatCompletion.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="Hello! How can I help you?"))],
                usage=MagicMock(to_dict=lambda: {'total_tokens': 30}),
                model='gpt-4.1',
                id='test-request-id'
            )
            
            response = client.post(
                '/api/ai-chats/send-message',
                headers=auth_headers,
                json={
                    'chat_id': test_chat.id,
                    'user_question': 'Hello, how are you?',
                    'ai_model': 'gpt-4.1'
                }
            )
            
            assert response.status_code == 201
            data = response.json
            assert data['success'] is True
            assert 'ai_chat' in data
            assert data['ai_chat']['user_question'] == 'Hello, how are you?'
            assert data['ai_chat']['ai_answer'] == 'Hello! How can I help you?'
    
    def test_get_ai_chat_endpoint(self, client, auth_headers, test_chat):
        """Test getting specific AI chat endpoint"""
        # Create AI chat first
        ai_chat = AIChat(
            chat_id=test_chat.id,
            user_id=1,
            user_question="Test question",
            ai_answer="Test answer",
            ai_model="gpt-4.1",
            ai_model_provider="OpenAI"
        )
        db.session.add(ai_chat)
        db.session.commit()
        
        response = client.get(
            f'/api/ai-chats/{ai_chat.id}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json
        assert data['id'] == ai_chat.id
        assert data['user_question'] == "Test question"
        assert data['ai_answer'] == "Test answer"
    
    def test_update_ai_chat_endpoint(self, client, auth_headers, test_chat):
        """Test updating AI chat endpoint"""
        # Create AI chat first
        ai_chat = AIChat(
            chat_id=test_chat.id,
            user_id=1,
            user_question="Original question",
            ai_answer="Original answer",
            ai_model="gpt-4.1",
            ai_model_provider="OpenAI"
        )
        db.session.add(ai_chat)
        db.session.commit()
        
        response = client.put(
            f'/api/ai-chats/{ai_chat.id}',
            headers=auth_headers,
            json={
                'user_question': 'Updated question',
                'ai_answer': 'Updated answer'
            }
        )
        
        assert response.status_code == 200
        data = response.json
        assert data['user_question'] == 'Updated question'
        assert data['ai_answer'] == 'Updated answer'
    
    def test_delete_ai_chat_endpoint(self, client, auth_headers, test_chat):
        """Test deleting AI chat endpoint"""
        # Create AI chat first
        ai_chat = AIChat(
            chat_id=test_chat.id,
            user_id=1,
            user_question="Test question",
            ai_answer="Test answer",
            ai_model="gpt-4.1",
            ai_model_provider="OpenAI"
        )
        db.session.add(ai_chat)
        db.session.commit()
        
        response = client.delete(
            f'/api/ai-chats/{ai_chat.id}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json
        assert 'message' in data
        
        # Verify soft delete
        deleted_chat = AIChat.query.filter_by(id=ai_chat.id).first()
        assert deleted_chat.is_deleted is True
    
    def test_get_ai_chat_stats_endpoint(self, client, auth_headers, test_chat):
        """Test getting AI chat statistics endpoint"""
        # Create some AI chats with stats
        for i in range(2):
            ai_chat = AIChat(
                chat_id=test_chat.id,
                user_id=1,
                user_question=f"Question {i}",
                ai_answer=f"Answer {i}",
                ai_model="gpt-4.1",
                ai_model_provider="OpenAI"
            )
            db.session.add(ai_chat)
            db.session.flush()
            
            ai_stats = AIStats(
                ai_chat_id=ai_chat.id,
                tokens_used=50 + i * 10,
                response_time_ms=1000 + i * 100
            )
            db.session.add(ai_stats)
        
        db.session.commit()
        
        response = client.get(
            '/api/ai-chats/stats',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json
        assert 'total_ai_chats' in data
        assert 'active_ai_chats' in data
        assert 'total_tokens_used' in data
        assert data['total_ai_chats'] == 2
    
    def test_health_check_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get('/api/ai-chats/health')
        
        assert response.status_code == 200
        data = response.json
        assert 'status' in data
        assert 'service' in data
        assert data['service'] == 'openai_chat'
    
    def test_unauthorized_access(self, client, test_chat):
        """Test unauthorized access to endpoints"""
        # Test without auth headers
        response = client.get(f'/api/chats/{test_chat.id}/ai-chats')
        assert response.status_code == 401
        
        response = client.post(
            f'/api/chats/{test_chat.id}/ai-chats',
            json={'user_question': 'Test question'}
        )
        assert response.status_code == 401
    
    def test_validation_errors(self, client, auth_headers, test_chat):
        """Test validation errors"""
        # Test missing required field
        response = client.post(
            f'/api/chats/{test_chat.id}/ai-chats',
            headers=auth_headers,
            json={}  # Missing user_question
        )
        assert response.status_code == 400
        data = response.json
        assert 'error' in data
        
        # Test empty user_question
        response = client.post(
            f'/api/chats/{test_chat.id}/ai-chats',
            headers=auth_headers,
            json={'user_question': ''}
        )
        assert response.status_code == 400


class TestOpenAIIntegration:
    """Test OpenAI API integration"""
    
    @patch('src.services.openai_chat_service.openai')
    def test_openai_api_success(self, mock_openai):
        """Test successful OpenAI API call"""
        # Mock successful response
        mock_openai.ChatCompletion.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="AI response"))],
            usage=MagicMock(to_dict=lambda: {'total_tokens': 50}),
            model='gpt-4.1',
            id='test-id'
        )
        
        service = OpenAIChatService()
        service.openai_client = mock_openai
        
        response = service._get_openai_response("Test question", "gpt-4.1")
        
        assert response.success is True
        assert response.content == "AI response"
        assert response.model == "gpt-4.1"
        assert response.usage['total_tokens'] == 50
    
    @patch('src.services.openai_chat_service.openai')
    def test_openai_api_error(self, mock_openai):
        """Test OpenAI API error handling"""
        # Mock API error
        mock_openai.ChatCompletion.create.side_effect = Exception("API Error")
        
        service = OpenAIChatService()
        service.openai_client = mock_openai
        
        response = service._get_openai_response("Test question", "gpt-4.1")
        
        assert response.success is False
        assert "API Error" in response.error
    
    def test_openai_client_not_initialized(self):
        """Test behavior when OpenAI client is not initialized"""
        service = OpenAIChatService()
        service.openai_client = None
        
        response = service._get_openai_response("Test question", "gpt-4.1")
        
        assert response.success is False
        assert "not initialized" in response.error


if __name__ == '__main__':
    pytest.main([__file__])


class TestOpenAIEndToEnd:
    """End-to-end test: create user -> project -> chat -> AIChat via HTTP API"""

    def test_full_cycle_create_user_project_chat_aichat(self, app, client):
        """Creates user, project, chat, and AIChat end-to-end using API (real OpenAI)."""
        import os
        if not os.getenv('OPENAI_API_KEY'):
            pytest.skip("OPENAI_API_KEY not set; skipping live E2E test")
        with app.app_context():

            # 1) Register user (ignore if already exists)
            client.post('/api/users/register', json={
                'email': 'e2e@example.com',
                'senha': 'e2e-password',
                'first_name': 'E2E',
                'last_name': 'User'
            })

            # 2) Login and get token
            login_resp = client.post('/api/users/login', json={
                'email': 'e2e@example.com',
                'senha': 'e2e-password'
            })
            assert login_resp.status_code == 200
            token = login_resp.json.get('token')
            assert token
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }

            # 3) Create project
            project_resp = client.post('/api/projects', headers=headers, json={
                'name': 'E2E Project',
                'description': 'End-to-end project'
            })
            assert project_resp.status_code == 201
            project_id = project_resp.json.get('id')
            assert isinstance(project_id, int)

            # 4) Create chat under project
            chat_resp = client.post('/api/chats', headers=headers, json={
                'name': 'E2E Chat',
                'project_id': project_id,
                'description': 'End-to-end chat'
            })
            assert chat_resp.status_code == 201
            chat_id = chat_resp.json.get('id')
            assert isinstance(chat_id, int)

            # 5) Create AIChat by sending a message
            send_resp = client.post('/api/ai-chats/send-message', headers=headers, json={
                'chat_id': chat_id,
                'user_question': 'In one sentence, what is a contract?',
                'ai_model': 'gpt-4.1'
            })
            assert send_resp.status_code == 201
            ai_chat = send_resp.json.get('ai_chat')
            assert ai_chat and isinstance(ai_chat.get('id'), int)
            assert ai_chat.get('chat_id') == chat_id
            assert isinstance(ai_chat.get('ai_answer'), str) and len(ai_chat.get('ai_answer')) > 0

            # 6) Verify list endpoint sees the AIChat
            list_resp = client.get(f'/api/chats/{chat_id}/ai-chats', headers=headers)
            assert list_resp.status_code == 200
            assert list_resp.json.get('pagination', {}).get('total', 0) >= 1

            # 7) Fetch specific AIChat
            ai_chat_id = ai_chat['id']
            get_resp = client.get(f'/api/ai-chats/{ai_chat_id}', headers=headers)
            assert get_resp.status_code == 200
            assert get_resp.json.get('id') == ai_chat_id

            # 8) Update AIChat
            upd_resp = client.put(
                f'/api/ai-chats/{ai_chat_id}',
                headers=headers,
                json={'user_question': 'E2E Updated question', 'ai_answer': 'E2E Updated answer'}
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json.get('user_question') == 'E2E Updated question'

            # 9) Delete then restore AIChat
            del_resp = client.delete(f'/api/ai-chats/{ai_chat_id}', headers=headers)
            assert del_resp.status_code == 200
            res_resp = client.post(f'/api/ai-chats/{ai_chat_id}/restore', headers=headers)
            assert res_resp.status_code == 200
            assert res_resp.json.get('id') == ai_chat_id

            # 10) Stats and health
            stats_resp = client.get(f'/api/ai-chats/stats?chat_id={chat_id}', headers=headers)
            assert stats_resp.status_code == 200
            health_resp = client.get('/api/ai-chats/health')
            assert health_resp.status_code == 200
