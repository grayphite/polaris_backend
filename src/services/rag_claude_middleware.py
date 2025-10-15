"""
RAG-Claude Integration Middleware

Middleware simples para integrar RAG ao ClaudeAIService existente
sem quebrar compatibilidade. Para uso nas rotas.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Import seguro do service Claude existente
try:
    from src.services.claude_ai_service import ClaudeAIService, AIResponse

    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    ClaudeAIService = None
    AIResponse = None

# Import seguro do módulo RAG
try:
    from rag.mcp_integration import MCPRAGIntegration

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    MCPRAGIntegration = None

# Import seguro do cache
try:
    from src.services.cache_service import CacheService

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    CacheService = None


class RAGClaudeMiddleware:
    """
    Middleware para integrar RAG ao Claude existente.
    Funciona como proxy transparente.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Inicializar componentes
        self.claude_service = None
        self.rag_integration = None
        self.cache_service = None

        # Status dos componentes
        self.claude_enabled = False
        self.rag_enabled = False
        self.cache_enabled = False

        self._initialize_components()

    def _initialize_components(self):
        """Inicializa componentes disponíveis"""

        # Claude service (obrigatório)
        if CLAUDE_AVAILABLE:
            try:
                self.claude_service = ClaudeAIService()
                self.claude_enabled = True
                self.logger.info("✅ Claude service inicializado")
            except Exception as e:
                self.logger.error(f"❌ Falha ao inicializar Claude: {e}")
        else:
            self.logger.error("❌ Claude service não disponível")

        # RAG integration (opcional)
        if RAG_AVAILABLE:
            try:
                self.rag_integration = MCPRAGIntegration()
                self.rag_enabled = self.rag_integration.is_rag_available()

                if self.rag_enabled:
                    self.logger.info("✅ RAG integration ativada")
                else:
                    self.logger.info("⚠️ RAG disponível mas não funcional")

            except Exception as e:
                self.logger.warning(f"⚠️ RAG integration falhou: {e}")
        else:
            self.logger.info("📦 RAG não instalado - usando Claude puro")

        # Cache service (opcional)
        if CACHE_AVAILABLE:
            try:
                self.cache_service = CacheService()
                self.cache_enabled = True
                self.logger.info("✅ Cache service ativado")
            except Exception as e:
                self.logger.warning(f"⚠️ Cache falhou: {e}")
        else:
            self.logger.info("📦 Cache não disponível")

    def chat(self, prompt: str, user_id: int = None,
             use_rag: bool = True, use_cache: bool = True) -> Dict[str, Any]:
        """
        Chat inteligente com RAG opcional.
        
        Args:
            prompt: Pergunta do usuário
            user_id: ID do usuário
            use_rag: Se deve tentar usar RAG
            use_cache: Se deve usar cache
            
        Returns:
            Dict com resposta e metadados
        """

        if not self.claude_enabled:
            return {
                'success': False,
                'error': 'Claude service não disponível',
                'content': '',
                'mode': 'error'
            }

        # Verificar cache primeiro
        if use_cache and self.cache_enabled:
            cached = self._get_from_cache(prompt, user_id, use_rag)
            if cached:
                return cached

        # Tentar RAG se solicitado e disponível
        if use_rag and self.rag_enabled:
            rag_result = self._try_rag_chat(prompt, user_id)
            if rag_result['success']:
                # Cache o resultado
                if use_cache and self.cache_enabled:
                    self._save_to_cache(prompt, user_id, rag_result, True)
                return rag_result

        # Fallback para Claude tradicional
        claude_result = self._claude_chat(prompt, user_id)

        # Cache o resultado
        if use_cache and self.cache_enabled:
            self._save_to_cache(prompt, user_id, claude_result, False)

        return claude_result

    def _try_rag_chat(self, prompt: str, user_id: int) -> Dict[str, Any]:
        """Tenta chat com RAG"""

        try:
            # Consulta RAG
            rag_response = self.rag_integration.juridical_query(
                query=prompt,
                max_chunks=5,
                similarity_threshold=0.6
            )

            if rag_response.get('success', False):
                # RAG funcionou, usar contexto enriquecido
                enhanced_prompt = rag_response.get('response', prompt)

                # Chat Claude com contexto RAG
                claude_response = self.claude_service.chat(
                    prompt=enhanced_prompt,
                    user_id=user_id
                )

                if claude_response.success:
                    return {
                        'success': True,
                        'content': claude_response.content,
                        'mode': 'rag_enhanced',
                        'rag_sources': rag_response.get('sources', []),
                        'rag_chunks': len(
                            rag_response.get('context_chunks', [])
                        ),
                        'usage': claude_response.usage,
                        'timestamp': datetime.now().isoformat()
                    }

            # RAG não encontrou contexto relevante
            return {
                'success': False,
                'error': 'RAG não encontrou contexto relevante',
                'mode': 'rag_failed'
            }

        except Exception as e:
            self.logger.warning(f"Erro no RAG chat: {e}")
            return {
                'success': False,
                'error': f'Erro no RAG: {str(e)}',
                'mode': 'rag_error'
            }

    def _claude_chat(self, prompt: str, user_id: int) -> Dict[str, Any]:
        """Chat Claude tradicional"""

        try:
            claude_response = self.claude_service.chat(
                prompt=prompt,
                user_id=user_id
            )

            if claude_response.success:
                return {
                    'success': True,
                    'content': claude_response.content,
                    'mode': 'claude_only',
                    'usage': getattr(claude_response, 'usage', {}),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'success': False,
                    'error': getattr(
                        claude_response, 'error', 'Erro desconhecido'
                    ),
                    'content': '',
                    'mode': 'claude_error'
                }

        except Exception as e:
            self.logger.error(f"Erro no Claude chat: {e}")
            return {
                'success': False,
                'error': 'Erro interno na IA',
                'content': ('Sistema temporariamente indisponível. '
                            'Tente novamente.'),
                'mode': 'critical_error'
            }

    def _get_from_cache(self, prompt: str, user_id: int,
                        with_rag: bool) -> Optional[Dict[str, Any]]:
        """Busca no cache"""

        try:
            cache_key = f"middleware_chat:{hash(prompt)}:{user_id}:{with_rag}"
            cached_data = self.cache_service.get(cache_key)

            if cached_data:
                cached_data['mode'] = 'cache_hit'
                cached_data['cache_hit'] = True
                return cached_data

        except Exception as e:
            self.logger.warning(f"Erro ao buscar cache: {e}")

        return None

    def _save_to_cache(self, prompt: str, user_id: int,
                       response: Dict[str, Any], with_rag: bool):
        """Salva no cache"""

        try:
            if response.get('success', False):
                cache_key = f"middleware_chat:{hash(prompt)}:{user_id}:{with_rag}"

                # Cache por 30 minutos
                self.cache_service.set(cache_key, response, ttl=1800)

        except Exception as e:
            self.logger.warning(f"Erro ao salvar cache: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Status do middleware"""

        status = {
            'claude_enabled': self.claude_enabled,
            'rag_enabled': self.rag_enabled,
            'cache_enabled': self.cache_enabled,
            'components': {
                'claude_available': CLAUDE_AVAILABLE,
                'rag_available': RAG_AVAILABLE,
                'cache_available': CACHE_AVAILABLE
            },
            'timestamp': datetime.now().isoformat()
        }

        # Detalhes do RAG se disponível
        if self.rag_integration:
            try:
                rag_status = self.rag_integration.get_rag_status()
                status['rag_details'] = rag_status
            except Exception as e:
                status['rag_error'] = str(e)

        return status

    def chat_with_fallback(self, prompt: str, user_id: int = None) -> Dict[str, Any]:
        """
        Chat com fallback robusto.
        Garante que sempre retorna uma resposta válida.
        """

        # Tentar RAG primeiro
        if self.rag_enabled:
            result = self.chat(prompt, user_id, use_rag=True)
            if result['success']:
                return result

        # Fallback para Claude puro
        if self.claude_enabled:
            result = self.chat(prompt, user_id, use_rag=False)
            if result['success']:
                return result

        # Fallback final
        return {
            'success': False,
            'error': 'Todos os services indisponíveis',
            'content': 'Sistema temporariamente indisponível. Tente novamente.',
            'mode': 'system_down'
        }


# Instância global para uso nas rotas
rag_claude_middleware = RAGClaudeMiddleware()


def get_rag_claude_middleware() -> RAGClaudeMiddleware:
    """
    Função para obter o middleware RAG-Claude.
    Use esta função nas rotas para chat inteligente.
    """
    return rag_claude_middleware


def smart_chat(prompt: str, user_id: int = None,
               prefer_rag: bool = True) -> Dict[str, Any]:
    """
    Função de conveniência para chat inteligente.
    
    Args:
        prompt: Pergunta do usuário
        user_id: ID do usuário
        prefer_rag: Se deve preferir RAG quando disponível
        
    Returns:
        Dict com resposta e metadados
    """
    return rag_claude_middleware.chat(
        prompt=prompt,
        user_id=user_id,
        use_rag=prefer_rag,
        use_cache=True
    )
