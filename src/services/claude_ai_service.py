"""
ClaudeAIService - Integração com Claude AI

Este service gerencia toda a comunicação com a API do Claude AI,
incluindo chat, geração de documentos e análise de estruturas jurídicas.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Any

import requests


@dataclass
class ChatMessage:
    """Estrutura de uma mensagem de chat"""
    role: str  # 'user' ou 'assistant'
    content: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class AIResponse:
    """Estrutura de resposta da IA"""
    success: bool
    content: str = ""
    error: str = ""
    usage: Dict = None
    context_used: List[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class ClaudeAIService:
    """Service para integração com Claude AI"""

    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-3-haiku-20240307"
        self.max_tokens = 1000
        self.logger = logging.getLogger(self.__class__.__name__)

        if not self.api_key:
            self.logger.warning("ANTHROPIC_API_KEY não configurada - modo simulação")

    def chat(self, prompt: str, user_id: int = None,
             context: List[str] = None) -> AIResponse:
        """
        Chat básico com Claude AI
        
        Args:
            prompt: Pergunta/prompt do usuário
            user_id: ID do usuário (para logging)
            context: Contexto adicional para enriquecer a resposta
            
        Returns:
            AIResponse com a resposta da IA
        """
        try:
            # Se não há API key, retornar resposta simulada
            if not self.api_key:
                return AIResponse(
                    success=True,
                    content=("Esta é uma resposta simulada do Claude AI. "
                             "Para ativar a IA real, configure "
                             f"ANTHROPIC_API_KEY. Seu prompt foi: {prompt}"),
                    usage={'tokens': 0}
                )

            # Construir prompt com contexto se fornecido
            enhanced_prompt = self._build_enhanced_prompt(prompt, context)

            # Preparar headers
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }

            # Preparar payload
            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [
                    {
                        "role": "user",
                        "content": enhanced_prompt
                    }
                ]
            }

            # Fazer requisição
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                content = data.get('content', [{}])[0].get('text', '')
                usage = data.get('usage', {})

                # Log da interação (se logging service estiver disponível)
                self._log_interaction(user_id, prompt, content, usage)

                return AIResponse(
                    success=True,
                    content=content,
                    usage=usage,
                    context_used=context or []
                )
            else:
                error_msg = f"Erro na API Claude: {response.status_code} - {response.text}"
                self._log_error(error_msg, user_id)

                return AIResponse(
                    success=False,
                    error="Erro na comunicação com IA. Tente novamente."
                )

        except requests.exceptions.Timeout:
            error_msg = "Timeout na comunicação com Claude AI"
            self._log_error(error_msg, user_id)
            return AIResponse(
                success=False,
                error="Timeout na comunicação com IA. Tente novamente."
            )

        except Exception as e:
            error_msg = f"Erro inesperado no Claude AI: {str(e)}"
            self._log_error(error_msg, user_id)
            return AIResponse(
                success=False,
                error="Erro interno. Tente novamente."
            )

    def chat_with_rag(self, prompt: str, user_id: int = None) -> AIResponse:
        """
        Chat com RAG (Retrieval-Augmented Generation)
        Busca contexto relevante antes de responder
        
        Args:
            prompt: Pergunta do usuário
            user_id: ID do usuário
            
        Returns:
            AIResponse com resposta enriquecida com contexto
        """
        try:
            # Buscar contexto relevante (se search service estiver disponível)
            relevant_context = self._get_relevant_context(prompt)

            # Chat com contexto
            return self.chat(prompt, user_id, relevant_context)

        except Exception as e:
            # Fallback para chat sem RAG
            return self.chat(prompt, user_id)

    def generate_document(self,
                          document_type: str,
                          client_data: Dict,
                          template_data: Dict = None,
                          user_id: int = None) -> AIResponse:
        """
        Gerar documento jurídico usando Claude AI
        
        Args:
            document_type: Tipo de documento (trust, estate, etc.)
            client_data: Dados do cliente
            template_data: Dados do template (opcional)
            user_id: ID do usuário
            
        Returns:
            AIResponse com documento gerado
        """
        try:
            # Construir prompt para geração de documento
            prompt = self._build_document_prompt(document_type, client_data, template_data)

            # Usar modelo mais avançado para documentos
            original_model = self.model
            original_max_tokens = self.max_tokens

            self.model = "claude-3-haiku-20240307"  # Modelo mais capaz
            self.max_tokens = 2000  # Mais tokens para documentos

            try:
                response = self.chat(prompt, user_id)
                return response
            finally:
                # Restaurar configurações originais
                self.model = original_model
                self.max_tokens = original_max_tokens

        except Exception as e:
            error_msg = f"Erro na geração de documento: {str(e)}"
            self._log_error(error_msg, user_id)
            return AIResponse(
                success=False,
                error="Erro na geração do documento. Tente novamente."
            )

    def analyze_legal_structure(self,
                                structure_data: Dict,
                                jurisdiction: str = None,
                                user_id: int = None) -> AIResponse:
        """
        Analisar estrutura jurídica e fornecer recomendações
        
        Args:
            structure_data: Dados da estrutura a ser analisada
            jurisdiction: Jurisdição (opcional)
            user_id: ID do usuário
            
        Returns:
            AIResponse com análise e recomendações
        """
        try:
            # Construir prompt para análise
            prompt = self._build_analysis_prompt(structure_data, jurisdiction)

            # Buscar contexto jurídico relevante
            legal_context = self._get_legal_context(structure_data, jurisdiction)

            return self.chat(prompt, user_id, legal_context)

        except Exception as e:
            error_msg = f"Erro na análise jurídica: {str(e)}"
            self._log_error(error_msg, user_id)
            return AIResponse(
                success=False,
                error="Erro na análise. Tente novamente."
            )

    def get_recommendations(self,
                            client_profile: Dict,
                            objectives: List[str],
                            user_id: int = None) -> AIResponse:
        """
        Obter recomendações personalizadas de wealth planning
        
        Args:
            client_profile: Perfil do cliente
            objectives: Objetivos do planejamento
            user_id: ID do usuário
            
        Returns:
            AIResponse com recomendações
        """
        try:
            # Construir prompt para recomendações
            prompt = self._build_recommendations_prompt(client_profile, objectives)

            # Buscar contexto de wealth planning
            wp_context = self._get_wealth_planning_context(client_profile)

            return self.chat(prompt, user_id, wp_context)

        except Exception as e:
            error_msg = f"Erro nas recomendações: {str(e)}"
            self._log_error(error_msg, user_id)
            return AIResponse(
                success=False,
                error="Erro ao gerar recomendações. Tente novamente."
            )

    def health_check(self) -> Dict[str, Any]:
        """
        Verificar saúde da integração com Claude AI
        
        Returns:
            Dict com status da integração
        """
        try:
            # Teste simples com a API
            test_response = self.chat("Hello", context=["Test"])

            return {
                "status": "healthy" if test_response.success else "unhealthy",
                "api_key_configured": bool(self.api_key),
                "model": self.model,
                "last_test": datetime.utcnow().isoformat(),
                "test_success": test_response.success,
                "error": test_response.error if not test_response.success else None
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "api_key_configured": bool(self.api_key),
                "model": self.model,
                "last_test": datetime.utcnow().isoformat(),
                "test_success": False,
                "error": str(e)
            }

    # Métodos privados auxiliares

    def _build_enhanced_prompt(self, prompt: str, context: List[str] = None) -> str:
        """Construir prompt enriquecido com contexto"""
        if not context:
            return f"""Você é um assistente especializado em wealth planning (planejamento patrimonial) para advogados tributaristas.

Responda de forma profissional e técnica, considerando:
- Estruturas offshore (trusts, holdings, etc.)
- Implicações fiscais no Brasil e internacionalmente
- Compliance e regulamentações
- Melhores práticas do setor

Pergunta: {prompt}"""

        context_text = "\n".join([f"- {ctx}" for ctx in context])

        return f"""Você é um assistente especializado em wealth planning (planejamento patrimonial) para advogados tributaristas.

CONTEXTO RELEVANTE:
{context_text}

Baseando-se no contexto acima e em seu conhecimento, responda de forma profissional e técnica, considerando:
- Estruturas offshore (trusts, holdings, etc.)
- Implicações fiscais no Brasil e internacionalmente
- Compliance e regulamentações
- Melhores práticas do setor

Pergunta: {prompt}"""

    def _build_document_prompt(self, document_type: str, client_data: Dict, template_data: Dict = None) -> str:
        """Construir prompt para geração de documento"""
        client_info = json.dumps(client_data, indent=2, ensure_ascii=False)

        return f"""Você é um especialista em documentos jurídicos para wealth planning.

Gere um documento profissional do tipo: {document_type.upper()}

DADOS DO CLIENTE:
{client_info}

INSTRUÇÕES:
1. Use linguagem jurídica apropriada
2. Inclua todas as cláusulas necessárias
3. Considere as melhores práticas internacionais
4. Adapte para a legislação brasileira quando aplicável
5. Formate de forma profissional

Gere o documento completo:"""

    def _build_analysis_prompt(self, structure_data: Dict, jurisdiction: str = None) -> str:
        """Construir prompt para análise jurídica"""
        structure_info = json.dumps(structure_data, indent=2, ensure_ascii=False)
        jurisdiction_text = f" na jurisdição {jurisdiction}" if jurisdiction else ""

        return f"""Você é um especialista em estruturas jurídicas internacionais.

Analise a seguinte estrutura{jurisdiction_text}:

ESTRUTURA:
{structure_info}

FORNEÇA:
1. Análise detalhada da estrutura
2. Vantagens e desvantagens
3. Riscos identificados
4. Recomendações de melhoria
5. Considerações fiscais
6. Aspectos de compliance

Análise:"""

    def _build_recommendations_prompt(self, client_profile: Dict, objectives: List[str]) -> str:
        """Construir prompt para recomendações"""
        profile_info = json.dumps(client_profile, indent=2, ensure_ascii=False)
        objectives_text = "\n".join([f"- {obj}" for obj in objectives])

        return f"""Você é um consultor especializado em wealth planning.

PERFIL DO CLIENTE:
{profile_info}

OBJETIVOS:
{objectives_text}

Forneça recomendações personalizadas incluindo:
1. Estruturas jurídicas recomendadas
2. Jurisdições mais adequadas
3. Estratégias fiscais
4. Cronograma de implementação
5. Riscos e mitigações
6. Próximos passos

Recomendações:"""

    def _get_relevant_context(self, prompt: str) -> List[str]:
        """Buscar contexto relevante para RAG"""
        try:
            # Aqui integraria com o SearchService quando implementado
            # Por enquanto, retorna contexto básico
            return [
                "Wealth planning envolve estruturas offshore para otimização fiscal",
                "Trusts são veículos comuns para proteção patrimonial",
                "Compliance internacional é crucial para estruturas offshore"
            ]
        except:
            return []

    def _get_legal_context(self, structure_data: Dict, jurisdiction: str = None) -> List[str]:
        """Buscar contexto jurídico específico"""
        try:
            # Aqui integraria com o LegalScrapingService quando implementado
            return [
                "Regulamentações internacionais sobre estruturas offshore",
                "Tratados de bitributação aplicáveis",
                "Requisitos de compliance por jurisdição"
            ]
        except:
            return []

    def _get_wealth_planning_context(self, client_profile: Dict) -> List[str]:
        """Buscar contexto de wealth planning"""
        try:
            # Contexto baseado no perfil do cliente
            context = []

            if client_profile.get('patrimonio_estimado', 0) > 10000000:
                context.append("Cliente high net worth - estruturas complexas recomendadas")

            if client_profile.get('nacionalidade') == 'brasileira':
                context.append("Considerações específicas para residentes fiscais brasileiros")

            return context
        except:
            return []

    def _log_interaction(self, user_id: int, prompt: str, response: str, usage: Dict):
        """Log da interação com IA"""
        try:
            # Aqui integraria com LoggingService quando implementado
            log_data = {
                'user_id': user_id,
                'prompt_length': len(prompt),
                'response_length': len(response),
                'usage': usage,
                'timestamp': datetime.utcnow().isoformat()
            }
            # logging_service.log_ai_interaction(log_data)
        except:
            pass

    def _log_error(self, error_msg: str, user_id: int = None):
        """Log de erro"""
        try:
            # Aqui integraria com LoggingService quando implementado
            log_data = {
                'error': error_msg,
                'user_id': user_id,
                'service': 'ClaudeAIService',
                'timestamp': datetime.utcnow().isoformat()
            }
            # logging_service.log_error(log_data)
            print(f"[ERROR] ClaudeAIService: {error_msg}")
        except:
            print(f"[ERROR] ClaudeAIService: {error_msg}")


# Instância global do service
claude_ai_service = ClaudeAIService()
