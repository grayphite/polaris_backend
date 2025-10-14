"""
ClienteService - Lógica de negócio para gestão de clientes

Este service gerencia todas as operações relacionadas aos clientes do POLARIS,
incluindo criação, atualização, busca e análise de perfil de risco.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from src.extensions import db
from src.models import Cliente

logger = logging.getLogger(__name__)


@dataclass
class ClienteResult:
    """Resultado de operação com cliente"""
    success: bool
    cliente: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ClienteService:
    """Service para gestão de clientes"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def criar_cliente(self, user_id: int, dados_cliente: Dict) -> ClienteResult:
        """
        Cria um novo cliente
        
        Args:
            user_id: ID do usuário responsável
            dados_cliente: Dados do cliente
        
        Returns:
            ClienteResult com resultado da operação
        """
        try:
            # Validar dados obrigatórios
            required_fields = ['nome', 'email']
            for field in required_fields:
                if field not in dados_cliente or not dados_cliente[field]:
                    return ClienteResult(
                        success=False,
                        error=f"Campo '{field}' é obrigatório"
                    )

            # Verificar se já existe cliente com mesmo email
            existing = Cliente.query.filter_by(
                email=dados_cliente['email']
            ).first()

            if existing:
                return ClienteResult(
                    success=False,
                    error="Já existe um cliente com este email"
                )

            # Criar novo cliente
            cliente = Cliente(
                nome=dados_cliente['nome'],
                email=dados_cliente['email'],
                telefone=dados_cliente.get('telefone'),
                cpf=dados_cliente.get('cpf'),
                endereco=dados_cliente.get('endereco'),
                data_nascimento=dados_cliente.get('data_nascimento'),
                estado_civil=dados_cliente.get('estado_civil'),
                profissao=dados_cliente.get('profissao'),
                renda_mensal=dados_cliente.get('renda_mensal'),
                patrimonio_total=dados_cliente.get('patrimonio_total'),
                objetivos_financeiros=dados_cliente.get('objetivos_financeiros'),
                perfil_risco=dados_cliente.get('perfil_risco', 'moderado'),
                user_id=user_id
            )

            db.session.add(cliente)
            db.session.commit()

            self.logger.info(f"Cliente criado: {cliente.id} - {cliente.nome}")

            return ClienteResult(
                success=True,
                cliente=cliente.to_dict(),
                message="Cliente criado com sucesso"
            )

        except Exception as e:
            db.session.rollback()
            error_msg = f"Erro ao criar cliente: {str(e)}"
            self.logger.error(error_msg)
            return ClienteResult(success=False, error=error_msg)

    def obter_cliente(self, cliente_id: int, user_id: int) -> ClienteResult:
        """
        Obtém dados de um cliente específico
        
        Args:
            cliente_id: ID do cliente
            user_id: ID do usuário (para verificação de permissão)
        
        Returns:
            ClienteResult com dados do cliente
        """
        try:
            cliente = Cliente.query.filter_by(
                id=cliente_id,
                user_id=user_id
            ).first()

            if not cliente:
                return ClienteResult(
                    success=False,
                    error="Cliente não encontrado"
                )

            return ClienteResult(
                success=True,
                cliente=cliente.to_dict()
            )

        except Exception as e:
            error_msg = f"Erro ao obter cliente: {str(e)}"
            self.logger.error(error_msg)
            return ClienteResult(success=False, error=error_msg)

    def listar_clientes(self, user_id: int, page: int = 1,
                        per_page: int = 20) -> Dict:
        """
        Lista clientes do usuário com paginação
        
        Args:
            user_id: ID do usuário
            page: Página atual
            per_page: Items por página
        
        Returns:
            Dict com lista de clientes e metadados de paginação
        """
        try:
            pagination = Cliente.query.filter_by(user_id=user_id).paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )

            clientes = [cliente.to_dict() for cliente in pagination.items]

            return {
                'success': True,
                'clientes': clientes,
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page,
                'per_page': per_page,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }

        except Exception as e:
            error_msg = f"Erro ao listar clientes: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'clientes': []
            }

    def atualizar_cliente(self, cliente_id: int, user_id: int,
                          dados: Dict) -> ClienteResult:
        """
        Atualiza dados de um cliente
        
        Args:
            cliente_id: ID do cliente
            user_id: ID do usuário
            dados: Novos dados do cliente
        
        Returns:
            ClienteResult com resultado da operação
        """
        try:
            cliente = Cliente.query.filter_by(
                id=cliente_id,
                user_id=user_id
            ).first()

            if not cliente:
                return ClienteResult(
                    success=False,
                    error="Cliente não encontrado"
                )

            # Atualizar campos permitidos
            allowed_fields = [
                'nome', 'email', 'telefone', 'cpf', 'endereco',
                'data_nascimento', 'estado_civil', 'profissao',
                'renda_mensal', 'patrimonio_total', 'objetivos_financeiros',
                'perfil_risco'
            ]

            for field in allowed_fields:
                if field in dados:
                    setattr(cliente, field, dados[field])

            cliente.updated_at = datetime.utcnow()
            db.session.commit()

            self.logger.info(f"Cliente atualizado: {cliente.id}")

            return ClienteResult(
                success=True,
                cliente=cliente.to_dict(),
                message="Cliente atualizado com sucesso"
            )

        except Exception as e:
            db.session.rollback()
            error_msg = f"Erro ao atualizar cliente: {str(e)}"
            self.logger.error(error_msg)
            return ClienteResult(success=False, error=error_msg)

    def deletar_cliente(self, cliente_id: int, user_id: int) -> ClienteResult:
        """
        Remove um cliente (soft delete)
        
        Args:
            cliente_id: ID do cliente
            user_id: ID do usuário
        
        Returns:
            ClienteResult com resultado da operação
        """
        try:
            cliente = Cliente.query.filter_by(
                id=cliente_id,
                user_id=user_id
            ).first()

            if not cliente:
                return ClienteResult(
                    success=False,
                    error="Cliente não encontrado"
                )

            # Soft delete - apenas marcar como inativo
            cliente.ativo = False
            cliente.updated_at = datetime.utcnow()
            db.session.commit()

            self.logger.info(f"Cliente removido: {cliente.id}")

            return ClienteResult(
                success=True,
                message="Cliente removido com sucesso"
            )

        except Exception as e:
            db.session.rollback()
            error_msg = f"Erro ao remover cliente: {str(e)}"
            self.logger.error(error_msg)
            return ClienteResult(success=False, error=error_msg)

    def analisar_perfil_risco(self, cliente_id: int,
                              user_id: int) -> Dict:
        """
        Analisa e sugere perfil de risco baseado nos dados do cliente
        
        Args:
            cliente_id: ID do cliente
            user_id: ID do usuário
        
        Returns:
            Dict com análise do perfil de risco
        """
        try:
            cliente = Cliente.query.filter_by(
                id=cliente_id,
                user_id=user_id
            ).first()

            if not cliente:
                return {
                    'success': False,
                    'error': 'Cliente não encontrado'
                }

            # Lógica simples de análise de perfil
            pontuacao = 0
            fatores = []

            # Idade (se disponível)
            if cliente.data_nascimento:
                idade = (datetime.now() - cliente.data_nascimento).days // 365
                if idade > 50:
                    pontuacao -= 1
                    fatores.append("Idade mais elevada sugere menor tolerância")
                elif idade < 30:
                    pontuacao += 1
                    fatores.append("Idade jovem permite maior tolerância")

            # Renda
            if cliente.renda_mensal:
                if cliente.renda_mensal > 10000:
                    pontuacao += 1
                    fatores.append("Renda elevada permite maior tolerância")
                elif cliente.renda_mensal < 3000:
                    pontuacao -= 1
                    fatores.append("Renda baixa sugere menor tolerância")

            # Patrimônio
            if cliente.patrimonio_total:
                if cliente.patrimonio_total > 100000:
                    pontuacao += 1
                    fatores.append("Patrimônio alto permite maior risco")

            # Determinar perfil sugerido
            if pontuacao >= 2:
                perfil_sugerido = "arrojado"
            elif pontuacao <= -2:
                perfil_sugerido = "conservador"
            else:
                perfil_sugerido = "moderado"

            return {
                'success': True,
                'cliente_id': cliente_id,
                'perfil_atual': cliente.perfil_risco,
                'perfil_sugerido': perfil_sugerido,
                'pontuacao': pontuacao,
                'fatores_analisados': fatores,
                'recomendacao': (f"Baseado na análise, sugerimos o perfil "
                                 f"'{perfil_sugerido}' para este cliente.")
            }

        except Exception as e:
            error_msg = f"Erro na análise de perfil: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }


# Instância global do service
cliente_service = ClienteService()
