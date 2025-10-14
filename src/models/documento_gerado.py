from datetime import datetime
from src.database import db

class DocumentoGerado(db.Model):
    """Modelo para documentos gerados pelo sistema POLARIS"""
    __tablename__ = 'documentos_gerados'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Informações básicas do documento
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    tipo_documento = db.Column(db.String(100), nullable=False)  # Trust, Will, LLC Agreement, etc.
    
    # Relacionamentos
    template_id = db.Column(db.Integer, db.ForeignKey('templates_documento.id'), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Conteúdo e dados
    conteudo_final = db.Column(db.Text, nullable=False)  # Documento final gerado
    dados_utilizados = db.Column(db.JSON)  # Dados do cliente utilizados na geração
    parametros_geracao = db.Column(db.JSON)  # Parâmetros específicos usados
    
    # Arquivo e formato
    formato_arquivo = db.Column(db.String(10), default='PDF')  # PDF, DOCX
    caminho_arquivo = db.Column(db.String(500))  # Caminho para o arquivo gerado
    tamanho_arquivo = db.Column(db.Integer)  # Tamanho em bytes
    hash_arquivo = db.Column(db.String(64))  # Hash SHA-256 para integridade
    
    # Status e workflow
    status = db.Column(db.String(50), default='Rascunho')  # Rascunho, Finalizado, Assinado, Arquivado
    versao = db.Column(db.Integer, default=1)
    requer_revisao = db.Column(db.Boolean, default=False)
    revisado_por = db.Column(db.Integer, db.ForeignKey('users.id'))
    data_revisao = db.Column(db.DateTime)
    
    # Assinatura e notarização
    requer_assinatura = db.Column(db.Boolean, default=False)
    assinado = db.Column(db.Boolean, default=False)
    data_assinatura = db.Column(db.DateTime)
    assinado_por = db.Column(db.String(200))  # Nome de quem assinou
    
    requer_notarizacao = db.Column(db.Boolean, default=False)
    notarizado = db.Column(db.Boolean, default=False)
    data_notarizacao = db.Column(db.DateTime)
    notario_info = db.Column(db.JSON)  # Informações do notário
    
    # Validade e compliance
    data_validade = db.Column(db.DateTime)  # Se o documento tem validade
    jurisdicao_aplicavel = db.Column(db.String(50))
    compliance_verificado = db.Column(db.Boolean, default=False)
    
    # Histórico e auditoria
    historico_alteracoes = db.Column(db.JSON)  # Log de alterações
    comentarios = db.Column(db.Text)  # Comentários e observações
    
    # Metadados
    is_active = db.Column(db.Boolean, default=True)
    is_confidencial = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos adicionais
    revisor = db.relationship('User', foreign_keys=[revisado_por], backref='documentos_revisados')

    def __repr__(self):
        return f'<DocumentoGerado {self.titulo}>'

    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'titulo': self.titulo,
            'descricao': self.descricao,
            'tipo_documento': self.tipo_documento,
            'template_id': self.template_id,
            'cliente_id': self.cliente_id,
            'user_id': self.user_id,
            'conteudo_final': self.conteudo_final,
            'dados_utilizados': self.dados_utilizados,
            'parametros_geracao': self.parametros_geracao,
            'formato_arquivo': self.formato_arquivo,
            'caminho_arquivo': self.caminho_arquivo,
            'tamanho_arquivo': self.tamanho_arquivo,
            'hash_arquivo': self.hash_arquivo,
            'status': self.status,
            'versao': self.versao,
            'requer_revisao': self.requer_revisao,
            'revisado_por': self.revisado_por,
            'data_revisao': self.data_revisao.isoformat() if self.data_revisao else None,
            'requer_assinatura': self.requer_assinatura,
            'assinado': self.assinado,
            'data_assinatura': self.data_assinatura.isoformat() if self.data_assinatura else None,
            'assinado_por': self.assinado_por,
            'requer_notarizacao': self.requer_notarizacao,
            'notarizado': self.notarizado,
            'data_notarizacao': self.data_notarizacao.isoformat() if self.data_notarizacao else None,
            'notario_info': self.notario_info,
            'data_validade': self.data_validade.isoformat() if self.data_validade else None,
            'jurisdicao_aplicavel': self.jurisdicao_aplicavel,
            'compliance_verificado': self.compliance_verificado,
            'historico_alteracoes': self.historico_alteracoes,
            'comentarios': self.comentarios,
            'is_active': self.is_active,
            'is_confidencial': self.is_confidencial,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def to_summary_dict(self):
        """Converte para dicionário resumido (para listagens)"""
        return {
            'id': self.id,
            'titulo': self.titulo,
            'tipo_documento': self.tipo_documento,
            'status': self.status,
            'versao': self.versao,
            'formato_arquivo': self.formato_arquivo,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

