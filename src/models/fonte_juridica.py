"""
Modelo para fontes jurídicas
"""
from datetime import datetime

from src.extensions import db


class FonteJuridica(db.Model):
    """Modelo para fontes jurídicas usadas pelo MCP service"""
    __tablename__ = 'fontes_juridicas'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500))
    tipo = db.Column(db.String(100))  # lei, jurisprudencia, doutrina, etc
    conteudo = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'url': self.url,
            'tipo': self.tipo,
            'conteudo': self.conteudo,
            'created_at': (self.created_at.isoformat()
                           if self.created_at else None),
            'updated_at': (self.updated_at.isoformat()
                           if self.updated_at else None)
        }
