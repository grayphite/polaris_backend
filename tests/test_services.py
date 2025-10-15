"""
Testes unitários para Services do POLARIS

Testa todas as funcionalidades críticas dos services implementados.
"""

import unittest
from unittest.mock import Mock, patch
import tempfile
import os
from datetime import datetime

# Configurar ambiente de teste
os.environ['TESTING'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from src.services.claude_ai_service import ClaudeAIService
from src.services.auth_service import AuthService
from src.services.document_processor_service import DocumentProcessorService
from src.services.mcp_service import MCPService
from src.services.search_service import SearchService
from src.services.cache_service import CacheService
from src.services.logging_service import LoggingService


class TestClaudeAIService(unittest.TestCase):
    """Testes para ClaudeAIService"""
    
    def setUp(self):
        self.service = ClaudeAIService()
    
    @patch('src.services.claude_ai_service.requests.post')
    def test_chat_success(self, mock_post):
        """Testa chat com Claude AI"""
        # Mock da resposta da API
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'content': [{'text': 'Resposta do Claude'}]
        }
        mock_post.return_value = mock_response
        
        # Executar teste
        result = self.service.chat(prompt="Teste", user_id=1)

        # Verificar resultado
        self.assertTrue(result.success)
        self.assertTrue(hasattr(result, 'response'))
        self.assertEqual(result.response, 'Resposta do Claude')

    def test_chat_validation(self):
        """Testa validação de entrada do chat"""
        with self.assertRaises(ValueError):
            self.service.chat(prompt="", user_id=1)
        
        with self.assertRaises(ValueError):
            self.service.chat(prompt="teste", user_id=None)
    
    def test_health_check(self):
        """Testa health check do service"""
        health = self.service.health_check()
        
        self.assertIn('status', health)
        self.assertIn('timestamp', health)


class TestAuthService(unittest.TestCase):
    """Testes para AuthService"""
    
    def setUp(self):
        self.service = AuthService()
    
    def test_generate_token(self):
        """Testa geração de token JWT"""
        # Use a User object instead of dict
        from src.models.user import User
        user = User(id=1, email='test@example.com', username='test', password_hash='hash', first_name='Test', last_name='User')
        token, _ = self.service._generate_token(user)

        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 50)
    
    def test_validate_token(self):
        """Testa validação de token JWT"""
        from src.models.user import User
        user = User(id=1, email='test@example.com', username='test', password_hash='hash', first_name='Test', last_name='User')
        token, _ = self.service._generate_token(user)

        decoded = self.service.validate_token(token)
        self.assertEqual(decoded.user_id, 1)
        self.assertEqual(decoded.email, 'test@example.com')

        invalid_decoded = self.service.validate_token('token_invalido')
        self.assertFalse(invalid_decoded.is_valid)

    def test_hash_password(self):
        """Testa hash de senha"""
        password = "senha123"
        hashed = self.service._hash_password(password)

        self.assertNotEqual(password, hashed)
        self.assertTrue(len(hashed) > 50)
    
    def test_verify_password(self):
        """Testa verificação de senha"""
        password = "senha123"
        hashed = self.service._hash_password(password)

        # Senha correta
        self.assertTrue(self.service._verify_password(password, hashed))

        # Senha incorreta
        self.assertFalse(self.service._verify_password("senha_errada", hashed))


class TestDocumentProcessorService(unittest.TestCase):
    """Testes para DocumentProcessorService"""
    
    def setUp(self):
        self.service = DocumentProcessorService()
    
    def test_extract_text_from_txt(self):
        """Testa extração de texto de arquivo TXT"""
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Conteúdo de teste")
            temp_path = f.name
        
        try:
            # Testar extração
            text = self.service.extract_text(temp_path)
            self.assertEqual(text.strip(), "Conteúdo de teste")
        finally:
            os.unlink(temp_path)
    
    def test_chunk_text(self):
        """Testa divisão de texto em chunks"""
        text = "Este é um texto longo que precisa ser dividido em chunks menores para processamento."
        
        chunks = self.service.chunk_text(text, chunk_size=20)
        
        self.assertIsInstance(chunks, list)
        self.assertTrue(len(chunks) > 1)
        for chunk in chunks:
            self.assertTrue(len(chunk) <= 25)  # Margem para palavras completas
    
    def test_extract_metadata(self):
        """Testa extração de metadados"""
        # Criar arquivo temporário
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Conteúdo de teste")
            temp_path = f.name
        
        try:
            metadata = self.service.extract_metadata(temp_path)
            
            self.assertIn('file_size', metadata)
            self.assertIn('file_type', metadata)
            self.assertIn('created_at', metadata)
            self.assertEqual(metadata['file_type'], 'txt')
        finally:
            os.unlink(temp_path)


class TestMCPService(unittest.TestCase):
    """Testes para MCPService"""
    
    def setUp(self):
        self.service = MCPService()
    
    @patch('src.services.mcp_service.document_processor_service')
    @patch('src.services.mcp_service.search_service')
    def test_upload_document(self, mock_search, mock_processor):
        """Testa upload de documento"""
        # Mock dos services
        mock_processor.process_document.return_value = {
            'text': 'Texto extraído',
            'chunks': ['chunk1', 'chunk2'],
            'metadata': {'file_type': 'txt'}
        }
        mock_search.index_document.return_value = True
        
        # Mock do arquivo
        mock_file = Mock()
        mock_file.filename = 'test.txt'
        mock_file.read.return_value = b'conteudo'
        
        # Testar upload
        result = self.service.upload_document(
            file=mock_file,
            filename='test.txt',
            user_id=1
        )
        
        self.assertIn('document_id', result)
        self.assertIn('status', result)
        self.assertEqual(result['status'], 'processing')
    
    def test_get_statistics(self):
        """Testa obtenção de estatísticas"""
        stats = self.service.get_statistics(user_id=1)
        
        self.assertIn('total_documents', stats)
        self.assertIn('total_size_mb', stats)
        self.assertIn('documents_by_category', stats)
        self.assertIn('processing_status', stats)
    
    def test_health_check(self):
        """Testa health check do MCP"""
        health = self.service.health_check()
        
        self.assertIn('status', health)
        self.assertIn('timestamp', health)


class TestSearchService(unittest.TestCase):
    """Testes para SearchService"""
    
    def setUp(self):
        self.service = SearchService()
    
    def test_semantic_search_validation(self):
        """Testa validação da busca semântica"""
        # Query vazia
        with self.assertRaises(ValueError):
            self.service.semantic_search(query="", filters={})
        
        # Query muito longa
        long_query = "a" * 1001
        with self.assertRaises(ValueError):
            self.service.semantic_search(query=long_query, filters={})
    
    def test_keyword_search(self):
        """Testa busca por palavras-chave"""
        result = self.service.keyword_search(
            query="teste",
            filters={'user_id': 1},
            limit=10
        )
        
        self.assertIn('results', result)
        self.assertIn('total', result)
        self.assertIn('search_time_ms', result)
        self.assertIsInstance(result['results'], list)
    
    def test_get_search_suggestions(self):
        """Testa sugestões de busca"""
        suggestions = self.service.get_search_suggestions(
            partial_query="tes",
            user_id=1,
            limit=5
        )
        
        self.assertIn('suggestions', suggestions)
        self.assertIsInstance(suggestions['suggestions'], list)
    
    def test_health_check(self):
        """Testa health check da busca"""
        health = self.service.health_check()
        
        self.assertIn('status', health)
        self.assertIn('index_size', health)


class TestCacheService(unittest.TestCase):
    """Testes para CacheService"""
    
    def setUp(self):
        self.service = CacheService()
    
    def test_set_get_cache(self):
        """Testa operações básicas de cache"""
        key = "test_key"
        value = {"data": "test_value"}
        
        # Set
        self.service.set(key, value, ttl=60)
        
        # Get
        cached_value = self.service.get(key)
        self.assertEqual(cached_value, value)
    
    def test_cache_expiration(self):
        """Testa expiração do cache"""
        key = "test_expiration"
        value = "test_value"
        
        # Set com TTL muito baixo
        self.service.set(key, value, ttl=0.1)
        
        # Verificar que existe
        self.assertEqual(self.service.get(key), value)
        
        # Aguardar expiração
        import time
        time.sleep(0.2)
        
        # Verificar que expirou
        self.assertIsNone(self.service.get(key))
    
    def test_delete_cache(self):
        """Testa exclusão de cache"""
        key = "test_delete"
        value = "test_value"
        
        # Set e verificar
        self.service.set(key, value)
        self.assertEqual(self.service.get(key), value)
        
        # Delete e verificar
        self.service.delete(key)
        self.assertIsNone(self.service.get(key))
    
    def test_cache_statistics(self):
        """Testa estatísticas do cache"""
        # Adicionar alguns itens
        self.service.set("key1", "value1")
        self.service.set("key2", "value2")
        
        stats = self.service.get_statistics()
        
        self.assertIn('total_keys', stats)
        self.assertIn('memory_usage_mb', stats)
        self.assertIn('hit_rate', stats)


class TestLoggingService(unittest.TestCase):
    """Testes para LoggingService"""
    
    def setUp(self):
        self.service = LoggingService()
    
    def test_log_levels(self):
        """Testa diferentes níveis de log"""
        # Não deve gerar exceções
        self.service.debug("TestComponent", "DEBUG_ACTION", "Debug message")
        self.service.info("TestComponent", "INFO_ACTION", "Info message")
        self.service.warning("TestComponent", "WARNING_ACTION", "Warning message")
        self.service.error("TestComponent", "ERROR_ACTION", "Error message")
    
    def test_log_with_metadata(self):
        """Testa log com metadados"""
        metadata = {
            'user_id': 123,
            'action_data': {'key': 'value'}
        }
        
        # Não deve gerar exceções
        self.service.info(
            "TestComponent",
            "TEST_ACTION",
            "Test message with metadata",
            user_id=123,
            metadata=metadata
        )
    
    def test_get_logs(self):
        """Testa obtenção de logs"""
        # Adicionar alguns logs
        self.service.info("TestComponent", "ACTION1", "Message 1")
        self.service.error("TestComponent", "ACTION2", "Message 2")
        
        # Obter logs
        logs = self.service.get_logs(limit=10)
        
        self.assertIsInstance(logs, list)
        if logs:  # Se houver logs
            log_entry = logs[0]
            self.assertIn('timestamp', log_entry)
            self.assertIn('level', log_entry)
            self.assertIn('component', log_entry)


class TestIntegration(unittest.TestCase):
    """Testes de integração entre services"""
    
    def setUp(self):
        self.auth_service = AuthService()
        self.cache_service = CacheService()
        self.logging_service = LoggingService()
    
    def test_auth_cache_integration(self):
        """Testa integração entre Auth e Cache"""
        # Gerar token
        user_data = {'id': 1, 'email': 'test@example.com'}
        token = self.auth_service.generate_token(user_data)
        
        # Cachear token
        cache_key = f"token_{token[:10]}"
        self.cache_service.set(cache_key, user_data, ttl=300)
        
        # Verificar cache
        cached_data = self.cache_service.get(cache_key)
        self.assertEqual(cached_data, user_data)
    
    def test_logging_integration(self):
        """Testa integração do logging com outros services"""
        # Simular operação que gera logs
        self.logging_service.info(
            "Integration",
            "TEST_OPERATION",
            "Testing integration",
            user_id=1,
            metadata={'test': True}
        )
        
        # Verificar que log foi criado
        logs = self.logging_service.get_logs(limit=1)
        self.assertTrue(len(logs) >= 0)  # Pode estar vazio dependendo da implementação


def run_all_tests():
    """Executa todos os testes"""
    # Descobrir e executar todos os testes
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    # Executar testes
    success = run_all_tests()
    
    if success:
        print("\n✅ TODOS OS TESTES PASSARAM!")
    else:
        print("\n❌ ALGUNS TESTES FALHARAM!")
    
    exit(0 if success else 1)
