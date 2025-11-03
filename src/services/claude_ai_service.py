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
        # Derive max output tokens from env and clamp to Claude limits
        try:
            env_max_out = int(os.getenv('ANTHROPIC_MAX_OUTPUT_TOKENS', '8192'))
        except Exception:
            env_max_out = 8192
        self.max_tokens = max(1, min(env_max_out, 8192))
        self.logger = logging.getLogger(self.__class__.__name__)

        if not self.api_key:
            self.logger.warning("ANTHROPIC_API_KEY não configurada - modo simulação")

    def chat(self, prompt: str, user_id: int = None,
             context: List[str] = None, rag_sources: List[Dict] = None) -> AIResponse:
        """
        Chat básico com Claude AI
        
        Args:
            prompt: Pergunta/prompt do usuário
            user_id: ID do usuário (para logging)
            context: Contexto adicional para enriquecer a resposta
            rag_sources: Fontes RAG para atribuição
            
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
            enhanced_prompt = self._build_enhanced_prompt(prompt, context, rag_sources)

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

    def _build_enhanced_prompt(self, prompt: str, context: List[str] = None, rag_sources: List[Dict] = None) -> str:
        """Construir prompt enriquecido com contexto"""
        if not context:
            return f"""You are a specialized assistant in wealth planning for tax lawyers.

Respond professionally and concisely, focusing only on relevant details. Keep responses brief and to the point.

Consider:
- Offshore structures (trusts, holdings, etc.)
- Tax implications in Brazil and internationally
- Compliance and regulations
- Industry best practices

Question: {prompt}"""

        context_text = "\n".join([f"- {ctx}" for ctx in context])
        
        # Build source attribution if RAG sources are provided
        source_attribution = ""
        if rag_sources:
            source_attribution = "\n\nIMPORTANT: When responding, always mention the sources of information when using the context above. Include:\n"
            source_attribution += "- Country/jurisdiction when applicable\n"
            source_attribution += "- Relevant section or chapter\n"
            source_attribution += "- Example: 'According to Law X of country Y, article Z...'\n"
            source_attribution += "- Be specific about the origin of the information\n\n"

        return f"""You are a specialized assistant in wealth planning for tax lawyers.

RELEVANT CONTEXT FOUND:
{context_text}
{source_attribution}Based on the context above and your knowledge, respond professionally and concisely, focusing only on relevant details. Keep responses brief and to the point.

Consider:
- Offshore structures (trusts, holdings, etc.)
- Tax implications in Brazil and internationally
- Compliance and regulations
- Industry best practices

Question: {prompt}"""

    def _build_document_prompt(self, document_type: str, client_data: Dict, template_data: Dict = None) -> str:
        """Construir prompt para geração de documento"""
        client_info = json.dumps(client_data, indent=2, ensure_ascii=False)

        return f"""You are an expert in legal documents for wealth planning.

Generate a professional document of type: {document_type.upper()}

CLIENT DATA:
{client_info}

INSTRUCTIONS:
1. Use appropriate legal language
2. Include all necessary clauses
3. Consider international best practices
4. Adapt to Brazilian legislation when applicable
5. Format professionally

Generate the complete document:"""

    def _build_analysis_prompt(self, structure_data: Dict, jurisdiction: str = None) -> str:
        """Construir prompt para análise jurídica"""
        structure_info = json.dumps(structure_data, indent=2, ensure_ascii=False)
        jurisdiction_text = f" in jurisdiction {jurisdiction}" if jurisdiction else ""

        return f"""You are an expert in international legal structures.

Analyze the following structure{jurisdiction_text}:

STRUCTURE:
{structure_info}

PROVIDE:
1. Detailed analysis of the structure
2. Advantages and disadvantages
3. Identified risks
4. Improvement recommendations
5. Tax considerations
6. Compliance aspects

Analysis:"""

    def _build_recommendations_prompt(self, client_profile: Dict, objectives: List[str]) -> str:
        """Construir prompt para recomendações"""
        profile_info = json.dumps(client_profile, indent=2, ensure_ascii=False)
        objectives_text = "\n".join([f"- {obj}" for obj in objectives])

        return f"""You are a specialized consultant in wealth planning.

CLIENT PROFILE:
{profile_info}

OBJECTIVES:
{objectives_text}

Provide personalized recommendations including:
1. Recommended legal structures
2. Most suitable jurisdictions
3. Tax strategies
4. Implementation timeline
5. Risks and mitigations
6. Next steps

Recommendations:"""

    def _get_relevant_context(self, prompt: str) -> List[str]:
        """Search for relevant context for RAG"""
        try:
            # Here would integrate with SearchService when implemented
            # For now, returns basic context
            return [
                "Wealth planning involves offshore structures for tax optimization",
                "Trusts are common vehicles for asset protection",
                "International compliance is crucial for offshore structures"
            ]
        except:
            return []

    def _get_legal_context(self, structure_data: Dict, jurisdiction: str = None) -> List[str]:
        """Search for specific legal context"""
        try:
            # Here would integrate with LegalScrapingService when implemented
            return [
                "International regulations on offshore structures",
                "Applicable double taxation treaties",
                "Compliance requirements by jurisdiction"
            ]
        except:
            return []

    def _get_wealth_planning_context(self, client_profile: Dict) -> List[str]:
        """Search for wealth planning context"""
        try:
            # Context based on client profile
            context = []

            if client_profile.get('patrimonio_estimado', 0) > 10000000:
                context.append("High net worth client - complex structures recommended")

            if client_profile.get('nacionalidade') == 'brasileira':
                context.append("Specific considerations for Brazilian tax residents")

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
