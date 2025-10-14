"""
Modelos para documentos e busca
"""
from datetime import datetime
from src.database import db


class DocumentoUpload(db.Model):
    """Modelo para documentos enviados pelos usuários"""
    __tablename__ = 'documentos_upload'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(100))
    tamanho = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'path': self.path,
            'tipo': self.tipo,
            'tamanho': self.tamanho,
            'user_id': self.user_id,
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None)
        }


class SearchIndex(db.Model):
    """Modelo para índice de busca"""
    __tablename__ = 'search_index'
    
    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey('documentos_upload.id'))
    conteudo = db.Column(db.Text)
    embedding = db.Column(db.Text)  # JSON serializado do embedding
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'documento_id': self.documento_id,
            'conteudo': self.conteudo,
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None)
        }


class LegalSource(db.Model):
    """Modelo para fontes legais scraped"""
    __tablename__ = 'legal_sources'
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False, unique=True)
    nome = db.Column(db.String(255))
    tipo = db.Column(db.String(100))
    status = db.Column(db.String(50), default='pending')
    last_scraped = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'nome': self.nome,
            'tipo': self.tipo,
            'status': self.status,
            'last_scraped': (self.last_scraped.isoformat()
                             if self.last_scraped else None),
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None)
        }


class ScrapedContent(db.Model):
    """Modelo para conteúdo extraído por scraping"""
    __tablename__ = 'scraped_content'
    
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey('legal_sources.id'))
    titulo = db.Column(db.String(255))
    conteudo = db.Column(db.Text)
    content_metadata = db.Column(db.Text)  # JSON serializado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'source_id': self.source_id,
            'titulo': self.titulo,
            'conteudo': self.conteudo,
            'metadata': self.content_metadata,
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None)
        }
