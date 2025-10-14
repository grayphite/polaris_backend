"""
POLARIS Services Layer

Este módulo contém todos os services (camada de lógica de negócio) do POLARIS.
Seguindo o padrão MVC + Services: Controllers (Routes) → Services → Models → Database

Services implementados:
- ClaudeAIService: Integração com Claude AI para chat e geração de documentos
- AuthService: Autenticação e autorização de usuários
- DocumentProcessorService: Upload e processamento de documentos PDF/DOC/TXT
- ClienteService: Lógica de negócio para gestão de clientes
- MCPService: Model Context Protocol para fontes jurídicas
- SearchService: Busca semântica e indexação
- PDFGeneratorService: Geração de documentos profissionais
- LegalScrapingService: Web scraping de fontes jurídicas
- CacheService: Cache com Redis para performance
- LoggingService: Sistema de logs e auditoria
- EmailService: Envio de notificações por email
- BackupService: Backup e recuperação de dados
"""

from .auth_service import AuthService
from .backup_service import BackupService
from .cache_service import CacheService
from .claude_ai_service import ClaudeAIService
from .cliente_service import ClienteService
from .document_processor_service import DocumentProcessorService
from .email_service import EmailService
from .legal_scraping_service import LegalScrapingService
from .logging_service import LoggingService
from .mcp_service import MCPService
from .pdf_generator_service import PDFGeneratorService
from .search_service import SearchService

# Instâncias globais dos services (Singleton pattern)
claude_ai_service = ClaudeAIService()
auth_service = AuthService()
document_processor_service = DocumentProcessorService()
cliente_service = ClienteService()
mcp_service = MCPService()
search_service = SearchService()
pdf_generator_service = PDFGeneratorService()
legal_scraping_service = LegalScrapingService()
cache_service = CacheService()
logging_service = LoggingService()
email_service = EmailService()
backup_service = BackupService()

__all__ = [
    'ClaudeAIService',
    'AuthService',
    'DocumentProcessorService',
    'ClienteService',
    'MCPService',
    'SearchService',
    'PDFGeneratorService',
    'LegalScrapingService',
    'CacheService',
    'LoggingService',
    'EmailService',
    'BackupService',
    # Instâncias
    'claude_ai_service',
    'auth_service',
    'document_processor_service',
    'cliente_service',
    'mcp_service',
    'search_service',
    'pdf_generator_service',
    'legal_scraping_service',
    'cache_service',
    'logging_service',
    'email_service',
    'backup_service'
]
