"""
Enhanced Claude AI Service - Integração RAG + Claude Otimizada

Este módulo estende o ClaudeAIService existente com capacidades RAG
sem quebrar a funcionalidade atual. Mantém compatibilidade total.
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any

# Imports seguros do sistema existente
from src.services.claude_ai_service import ClaudeAIService, AIResponse

# Import seguro do módulo RAG
try:
    from rag.mcp_integration import MCPRAGIntegration

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    MCPRAGIntegration = None

# Import seguro do cache service
try:
    from src.services.cache_service import CacheService

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    CacheService = None


@dataclass
class EnhancedAIResponse(AIResponse):
    """Resposta AI enriquecida com metadados RAG"""
    rag_used: bool = False
    rag_sources: List[str] = None
    rag_chunks_count: int = 0
    rag_processing_time: float = 0.0
    cache_hit: bool = False
    processing_mode: str = "claude_only"  # claude_only, rag_enhanced, cache_hit

    def __post_init__(self):
        super().__post_init__()
        if self.rag_sources is None:
            self.rag_sources = []


class EnhancedClaudeAIService:
    """
    Service Claude AI aprimorado com RAG otimizado.
    Mantém compatibilidade 100% com ClaudeAIService original.
    """

    def __init__(self):
        """Inicializa service com componentes opcionais"""
        # Service Claude original (sempre disponível)
        self.claude_service = ClaudeAIService()

        # RAG integration (opcional)
        self.rag_integration = None
        self.rag_enabled = False

        if RAG_AVAILABLE:
            try:
                self.rag_integration = MCPRAGIntegration()
                self.rag_enabled = self.rag_integration.is_rag_available()
                logging.info("✅ RAG integration ativada")
            except Exception as e:
                logging.warning(f"RAG integration falhou: {e}")
        else:
            logging.info("📦 RAG não disponível - usando Claude tradicional")

        # Cache service (opcional)
        self.cache_service = None
        self.cache_enabled = False

        if CACHE_AVAILABLE:
            try:
                self.cache_service = CacheService()
                self.cache_enabled = True
                logging.info("✅ Cache service ativado")
            except Exception as e:
                logging.warning(f"Cache service falhou: {e}")
        else:
            logging.info("📦 Cache não disponível")

        # Configurações
        self.enable_rag_by_default = True
        self.cache_ttl_minutes = 30
        self.rag_similarity_threshold = 0.05
        self.max_rag_chunks = 5

        self.logger = logging.getLogger(self.__class__.__name__)

    def chat(self, prompt: str, user_id: int = None,
             context: List[str] = None, use_rag: bool = None,
             use_cache: bool = True) -> EnhancedAIResponse:
        """
        Chat inteligente com RAG + Cache otimizado.
        Mantém assinatura compatível com ClaudeAIService original.
        
        Args:
            prompt: Pergunta/prompt do usuário
            user_id: ID do usuário (para logging e cache)
            context: Contexto adicional (manual)
            use_rag: Se deve usar RAG (None = auto, True = forçar, False = desabilitar)
            use_cache: Se deve usar cache
            
        Returns:
            EnhancedAIResponse com metadados completos
        """
        start_time = datetime.now()

        # Determinar se usar RAG
        should_use_rag = self._should_use_rag(use_rag, prompt)

        # Verificar cache primeiro
        if use_cache and self.cache_enabled:
            cached_response = self._get_cached_response(prompt, user_id, should_use_rag)
            if cached_response:
                return cached_response

        try:
            # Fluxo RAG-enhanced
            if should_use_rag and self.rag_enabled:
                return self._rag_enhanced_chat(prompt, user_id, context, start_time)

            # Fluxo Claude tradicional
            else:
                return self._traditional_chat(prompt, user_id, context, start_time)

        except Exception as e:
            self.logger.error(f"Erro no chat enhanced: {e}")
            # Fallback seguro para Claude original
            return self._fallback_chat(prompt, user_id, context, start_time)

    def chat_with_rag(self, prompt: str, user_id: int = None,
                      max_chunks: int = None,
                      similarity_threshold: float = None) -> EnhancedAIResponse:
        """
        Chat garantindo uso do RAG.
        Interface específica para consultas que requerem contexto jurídico.
        
        Args:
            prompt: Pergunta do usuário
            user_id: ID do usuário
            max_chunks: Máximo de chunks RAG (default: 5)
            similarity_threshold: Limite de similaridade (default: 0.05)
            
        Returns:
            EnhancedAIResponse com contexto RAG
        """
        # Configurar parâmetros RAG temporários
        original_max_chunks = self.max_rag_chunks
        original_threshold = self.rag_similarity_threshold

        if max_chunks:
            self.max_rag_chunks = max_chunks
        if similarity_threshold:
            self.rag_similarity_threshold = similarity_threshold

        try:
            # Forçar uso do RAG
            response = self.chat(prompt, user_id, use_rag=True, use_cache=True)
            return response

        finally:
            # Restaurar configurações originais
            self.max_rag_chunks = original_max_chunks
            self.rag_similarity_threshold = original_threshold

    def _should_use_rag(self, use_rag: Optional[bool], prompt: str) -> bool:
        """Determina se deve usar RAG baseado em heurísticas"""

        # Se explicitamente especificado
        if use_rag is not None:
            return use_rag and self.rag_enabled

        # Se RAG não disponível
        if not self.rag_enabled:
            return False

        # Heurísticas para determinar se prompt se beneficia de RAG
        jurídical_keywords = [
            'lei', 'artigo', 'código', 'jurisprudência', 'stf', 'stj',
            'direito', 'legal', 'norma', 'decreto', 'constituição',
            'precedente', 'súmula', 'acórdão', 'processo', 'tribunal'
        ]

        prompt_lower = prompt.lower()
        has_juridical_content = any(keyword in prompt_lower for keyword in jurídical_keywords)

        # Se prompt é longo (>50 chars) e tem conteúdo jurídico, usar RAG
        if len(prompt) > 50 and has_juridical_content:
            return True

        # Default: usar RAG se habilitado por padrão
        return self.enable_rag_by_default

    def _rag_enhanced_chat(self, prompt: str, user_id: int,
                           context: List[str], start_time: datetime) -> EnhancedAIResponse:
        """Chat com contexto RAG"""

        try:
            # Buscar contexto RAG
            rag_start = datetime.now()
            rag_response = self.rag_integration.juridical_query(
                query=prompt,
                max_chunks=self.max_rag_chunks,
                similarity_threshold=self.rag_similarity_threshold
            )
            rag_time = (datetime.now() - rag_start).total_seconds()

            if rag_response.get('success', False):
                # RAG encontrou contexto relevante
                enhanced_context = context or []

                # Adicionar contexto RAG
                if rag_response.get('context_chunks'):
                    enhanced_context.extend(rag_response['context_chunks'])

                # Chat Claude com contexto RAG
                claude_response = self.claude_service.chat(
                    prompt=prompt,
                    user_id=user_id,
                    context=enhanced_context
                )

                # Cache da resposta
                self._cache_response(prompt, user_id, claude_response, True)

                # Converter para EnhancedAIResponse
                return EnhancedAIResponse(
                    success=claude_response.success,
                    content=claude_response.content,
                    error=claude_response.error,
                    usage=claude_response.usage,
                    context_used=claude_response.context_used,
                    timestamp=claude_response.timestamp,
                    rag_used=True,
                    rag_sources=rag_response.get('sources', []),
                    rag_chunks_count=len(rag_response.get('context_chunks', [])),
                    rag_processing_time=rag_time,
                    processing_mode="rag_enhanced"
                )

            else:
                # RAG falhou, usar Claude tradicional
                self.logger.warning(f"RAG falhou: {rag_response.get('error', 'Erro desconhecido')}")
                return self._traditional_chat(prompt, user_id, context, start_time)

        except Exception as e:
            self.logger.error(f"Erro no RAG enhanced chat: {e}")
            return self._traditional_chat(prompt, user_id, context, start_time)

    def _traditional_chat(self, prompt: str, user_id: int,
                          context: List[str], start_time: datetime) -> EnhancedAIResponse:
        """Chat Claude tradicional"""

        try:
            claude_response = self.claude_service.chat(
                prompt=prompt,
                user_id=user_id,
                context=context
            )

            # Cache da resposta
            self._cache_response(prompt, user_id, claude_response, False)

            # Converter para EnhancedAIResponse
            return EnhancedAIResponse(
                success=claude_response.success,
                content=claude_response.content,
                error=claude_response.error,
                usage=claude_response.usage,
                context_used=claude_response.context_used,
                timestamp=claude_response.timestamp,
                rag_used=False,
                processing_mode="claude_only"
            )

        except Exception as e:
            self.logger.error(f"Erro no chat tradicional: {e}")
            return EnhancedAIResponse(
                success=False,
                error="Erro na comunicação com IA",
                processing_mode="error"
            )

    def _fallback_chat(self, prompt: str, user_id: int,
                       context: List[str], start_time: datetime) -> EnhancedAIResponse:
        """Fallback seguro para qualquer erro"""

        try:
            # Tentar Claude service original como último recurso
            claude_response = self.claude_service.chat(prompt, user_id, context)

            return EnhancedAIResponse(
                success=claude_response.success,
                content=claude_response.content,
                error=claude_response.error,
                usage=claude_response.usage,
                context_used=claude_response.context_used,
                timestamp=claude_response.timestamp,
                processing_mode="fallback"
            )

        except Exception as e:
            self.logger.error(f"Fallback também falhou: {e}")
            return EnhancedAIResponse(
                success=False,
                error="Sistema temporariamente indisponível",
                processing_mode="critical_error"
            )

    def _get_cached_response(self, prompt: str, user_id: int,
                             with_rag: bool) -> Optional[EnhancedAIResponse]:
        """Busca resposta no cache"""

        if not self.cache_enabled:
            return None

        try:
            # Chave de cache inclui hash do prompt + rag flag
            cache_key = f"chat:{hash(prompt)}:{user_id}:{with_rag}"

            cached_data = self.cache_service.get(cache_key)
            if cached_data:
                # Converter dict de volta para EnhancedAIResponse
                response_data = cached_data.copy()
                response_data['cache_hit'] = True
                response_data['processing_mode'] = "cache_hit"

                return EnhancedAIResponse(**response_data)

        except Exception as e:
            self.logger.warning(f"Erro ao buscar cache: {e}")

        return None

    def _cache_response(self, prompt: str, user_id: int,
                        response: AIResponse, with_rag: bool):
        """Salva resposta no cache"""

        if not self.cache_enabled or not response.success:
            return

        try:
            cache_key = f"chat:{hash(prompt)}:{user_id}:{with_rag}"

            # Converter para dict para serialização
            if isinstance(response, EnhancedAIResponse):
                cache_data = asdict(response)
            else:
                # Converter AIResponse para EnhancedAIResponse
                cache_data = {
                    'success': response.success,
                    'content': response.content,
                    'error': response.error,
                    'usage': response.usage,
                    'context_used': response.context_used,
                    'timestamp': response.timestamp,
                    'rag_used': with_rag,
                    'rag_sources': [],
                    'rag_chunks_count': 0,
                    'rag_processing_time': 0.0,
                    'cache_hit': False,
                    'processing_mode': "rag_enhanced" if with_rag else "claude_only"
                }

            # Cache por 30 minutos
            self.cache_service.set(
                cache_key,
                cache_data,
                ttl=self.cache_ttl_minutes * 60
            )

        except Exception as e:
            self.logger.warning(f"Erro ao salvar cache: {e}")

    def get_system_status(self) -> Dict[str, Any]:
        """Status completo do sistema enhanced"""

        status = {
            'claude_service': True,  # Sempre disponível
            'rag_available': RAG_AVAILABLE,
            'rag_enabled': self.rag_enabled,
            'cache_available': CACHE_AVAILABLE,
            'cache_enabled': self.cache_enabled,
            'timestamp': datetime.now().isoformat()
        }

        # Status do RAG se disponível
        if self.rag_integration:
            try:
                rag_status = self.rag_integration.get_rag_status()
                status['rag_details'] = rag_status
            except Exception as e:
                status['rag_error'] = str(e)

        # Status do cache se disponível
        if self.cache_service:
            try:
                status['cache_stats'] = self.cache_service.get_stats()
            except Exception as e:
                status['cache_error'] = str(e)

        return status

    def configure_rag(self, enabled: bool = None,
                      similarity_threshold: float = None,
                      max_chunks: int = None):
        """Configurar parâmetros RAG dinamicamente"""

        if enabled is not None:
            self.enable_rag_by_default = enabled

        if similarity_threshold is not None:
            self.rag_similarity_threshold = similarity_threshold

        if max_chunks is not None:
            self.max_rag_chunks = max_chunks

        self.logger.info(f"RAG reconfigurado: enabled={self.enable_rag_by_default}, "
                         f"threshold={self.rag_similarity_threshold}, "
                         f"max_chunks={self.max_rag_chunks}")

    # Métodos de compatibilidade com ClaudeAIService original
    def generate_document(self, document_type: str, client_data: Dict,
                          template_data: Dict = None, user_id: int = None) -> AIResponse:
        """Proxy para generate_document do ClaudeAIService original"""
        return self.claude_service.generate_document(
            document_type, client_data, template_data, user_id
        )

    def analyze_legal_structure(self, structure_data: Dict,
                                jurisdiction: str = None, user_id: int = None) -> AIResponse:
        """Proxy para analyze_legal_structure do ClaudeAIService original"""
        return self.claude_service.analyze_legal_structure(
            structure_data, jurisdiction, user_id
        )

    def get_recommendations(self, client_profile: Dict,
                            objectives: List[str], user_id: int = None) -> AIResponse:
        """Proxy para get_recommendations do ClaudeAIService original"""
        return self.claude_service.get_recommendations(
            client_profile, objectives, user_id
        )

    def health_check(self) -> Dict[str, Any]:
        """Health check combinado"""
        claude_health = self.claude_service.health_check()
        enhanced_status = self.get_system_status()

        return {
            'claude_service': claude_health,
            'enhanced_features': enhanced_status,
            'overall_status': 'healthy' if claude_health.get('status') == 'healthy' else 'degraded'
        }


# Instância global para compatibilidade
enhanced_claude_service = EnhancedClaudeAIService()


# Função de conveniência para migração gradual
def get_enhanced_claude_service() -> EnhancedClaudeAIService:
    """
    Retorna instância do Enhanced Claude Service.
    Use esta função para obter o service com capacidades RAG.
    """
    return enhanced_claude_service


def get_compatible_claude_service() -> ClaudeAIService:
    """
    Retorna o ClaudeAIService original para compatibilidade total.
    Use quando precisar da interface exata do service original.
    """
    return ClaudeAIService()
