from src.database import db
from datetime import datetime


class TemplateDeDocumento(db.Model):
    """Modelo para templates de documentos jurídicos do POLARIS"""
    __tablename__ = 'templates_documento'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Informações básicas do template
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    categoria = db.Column(db.String(100), nullable=False)  # Trust, Estate, International, Corporate
    subcategoria = db.Column(db.String(100))  # GRAT, ILIT, LLC, etc.
    
    # Jurisdição e aplicabilidade
    jurisdicao = db.Column(db.String(50))  # EUA, Brasil, Cayman, etc.
    estado_jurisdicao = db.Column(db.String(50))  # Delaware, Nevada, etc.
    
    # Conteúdo do template
    conteudo_template = db.Column(db.Text, nullable=False)  # Template com placeholders
    placeholders = db.Column(db.JSON)  # Lista de placeholders e suas descrições
    
    # Configurações de geração
    formato_saida = db.Column(db.String(10), default='PDF')  # PDF, DOCX
    requer_assinatura = db.Column(db.Boolean, default=False)
    requer_notarizacao = db.Column(db.Boolean, default=False)
    
    # Complexidade e requisitos
    nivel_complexidade = db.Column(db.String(20))  # Básico, Intermediário, Avançado
    patrimonio_minimo = db.Column(db.Numeric(15, 2))  # Patrimônio mínimo recomendado
    patrimonio_maximo = db.Column(db.Numeric(15, 2))  # Patrimônio máximo recomendado
    
    # Informações legais
    base_legal = db.Column(db.Text)  # Referências legais e regulamentações
    consideracoes_fiscais = db.Column(db.Text)  # Implicações fiscais importantes
    
    # Metadados
    versao = db.Column(db.String(10), default='1.0')
    is_active = db.Column(db.Boolean, default=True)
    is_public = db.Column(db.Boolean, default=True)  # Se está disponível para todos os usuários
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    documentos_gerados = db.relationship('DocumentoGerado', backref='template', lazy=True)
    creator = db.relationship('User', backref='templates_criados', foreign_keys=[created_by])

    def __repr__(self):
        return f'<TemplateDeDocumento {self.nome}>'

    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'categoria': self.categoria,
            'subcategoria': self.subcategoria,
            'jurisdicao': self.jurisdicao,
            'estado_jurisdicao': self.estado_jurisdicao,
            'conteudo_template': self.conteudo_template,
            'placeholders': self.placeholders,
            'formato_saida': self.formato_saida,
            'requer_assinatura': self.requer_assinatura,
            'requer_notarizacao': self.requer_notarizacao,
            'nivel_complexidade': self.nivel_complexidade,
            'patrimonio_minimo': float(self.patrimonio_minimo) if self.patrimonio_minimo else None,
            'patrimonio_maximo': float(self.patrimonio_maximo) if self.patrimonio_maximo else None,
            'base_legal': self.base_legal,
            'consideracoes_fiscais': self.consideracoes_fiscais,
            'versao': self.versao,
            'is_active': self.is_active,
            'is_public': self.is_public,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def to_summary_dict(self):
        """Converte para dicionário resumido (para listagens)"""
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'categoria': self.categoria,
            'subcategoria': self.subcategoria,
            'jurisdicao': self.jurisdicao,
            'nivel_complexidade': self.nivel_complexidade,
            'versao': self.versao,
            'is_active': self.is_active
        }

