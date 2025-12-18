from datetime import datetime

from src.extensions import db


class Cliente(db.Model):
    """Modelo para clientes do sistema POLARIS"""
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)

    # Dados pessoais básicos
    nome_completo = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    telefone = db.Column(db.String(20))
    data_nascimento = db.Column(db.Date)
    nacionalidade = db.Column(db.String(50))

    # Documentos
    cpf = db.Column(db.String(14))  # Formato: 000.000.000-00
    passaporte = db.Column(db.String(20))
    rg = db.Column(db.String(20))

    # Endereço
    endereco_completo = db.Column(db.Text)
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(50))
    cep = db.Column(db.String(10))
    pais = db.Column(db.String(50))

    # Informações profissionais
    profissao = db.Column(db.String(100))
    empresa = db.Column(db.String(200))
    cargo = db.Column(db.String(100))

    # Informações financeiras
    renda_anual = db.Column(db.Numeric(15, 2))
    patrimonio_total = db.Column(db.Numeric(15, 2))
    origem_patrimonio = db.Column(db.Text)  # História de construção do patrimônio

    # Status de residência fiscal
    residente_fiscal_brasil = db.Column(db.Boolean, default=True)
    residente_fiscal_eua = db.Column(db.Boolean, default=False)
    outros_paises_residencia = db.Column(db.Text)

    # Objetivos de planejamento
    objetivos_planejamento = db.Column(db.Text)
    tolerancia_risco = db.Column(db.String(20))  # Baixa, Média, Alta
    horizonte_investimento = db.Column(db.String(50))  # Curto, Médio, Longo prazo

    # Estruturas existentes
    possui_offshore = db.Column(db.Boolean, default=False)
    detalhes_offshore = db.Column(db.Text)
    possui_trust = db.Column(db.Boolean, default=False)
    detalhes_trust = db.Column(db.Text)

    # Metadados
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    documentos_gerados = db.relationship('DocumentoGerado', backref='cliente', lazy=True)

    def __repr__(self):
        return f'<Cliente {self.nome_completo}>'

    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'nome_completo': self.nome_completo,
            'email': self.email,
            'telefone': self.telefone,
            'data_nascimento': self.data_nascimento.isoformat() if self.data_nascimento else None,
            'nacionalidade': self.nacionalidade,
            'cpf': self.cpf,
            'passaporte': self.passaporte,
            'rg': self.rg,
            'endereco_completo': self.endereco_completo,
            'cidade': self.cidade,
            'estado': self.estado,
            'cep': self.cep,
            'pais': self.pais,
            'profissao': self.profissao,
            'empresa': self.empresa,
            'cargo': self.cargo,
            'renda_anual': float(self.renda_anual) if self.renda_anual else None,
            'patrimonio_total': float(self.patrimonio_total) if self.patrimonio_total else None,
            'origem_patrimonio': self.origem_patrimonio,
            'residente_fiscal_brasil': self.residente_fiscal_brasil,
            'residente_fiscal_eua': self.residente_fiscal_eua,
            'outros_paises_residencia': self.outros_paises_residencia,
            'objetivos_planejamento': self.objetivos_planejamento,
            'tolerancia_risco': self.tolerancia_risco,
            'horizonte_investimento': self.horizonte_investimento,
            'possui_offshore': self.possui_offshore,
            'detalhes_offshore': self.detalhes_offshore,
            'possui_trust': self.possui_trust,
            'detalhes_trust': self.detalhes_trust,
            'user_id': self.user_id,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def to_summary_dict(self):
        """Converte para dicionário resumido (para listagens)"""
        return {
            'id': self.id,
            'nome_completo': self.nome_completo,
            'email': self.email,
            'telefone': self.telefone,
            'patrimonio_total': float(self.patrimonio_total) if self.patrimonio_total else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
