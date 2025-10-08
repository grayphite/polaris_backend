"""
Modelos de dados do POLARIS
"""

from .user import User
from .cliente import Cliente
from .template_documento import TemplateDeDocumento
from .documento_gerado import DocumentoGerado
from .fonte_juridica import FonteJuridica
from .audit_log import AuditLog
from .documents import (
    DocumentoUpload, SearchIndex, LegalSource, ScrapedContent
)

__all__ = [
    'User', 'Cliente', 'TemplateDeDocumento', 'DocumentoGerado',
    'FonteJuridica', 'AuditLog', 'DocumentoUpload', 'SearchIndex',
    'LegalSource', 'ScrapedContent'
]

