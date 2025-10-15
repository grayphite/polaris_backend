"""
Modelos de dados do POLARIS
"""

from .audit_log import AuditLog
from .cliente import Cliente
from .documento_gerado import DocumentoGerado
from .documents import (
    DocumentoUpload, SearchIndex, LegalSource, ScrapedContent
)
from .fonte_juridica import FonteJuridica
from .template_documento import TemplateDeDocumento
from .user import User
from .project import Project

__all__ = [
    'User', 'Cliente', 'TemplateDeDocumento', 'DocumentoGerado',
    'FonteJuridica', 'AuditLog', 'DocumentoUpload', 'SearchIndex',
    'LegalSource', 'ScrapedContent', 'Project'
]
