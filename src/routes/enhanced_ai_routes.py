"""
Enhanced AI Routes - Rotas AI com RAG integrado

Extensão das rotas AI existentes com capacidades RAG otimizadas.
Mantém compatibilidade com rotas originais.
"""

import time
from functools import wraps

from flask import Blueprint, request, jsonify

# Imports seguros do sistema existente
try:
    from src.services.auth_service import auth_service, require_auth
    from src.services.logging_service import logging_service, LogLevel, ActionType, log_action
    from src.services.cache_service import cache_service

    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False

# Import do middleware RAG-Claude
from src.services.rag_claude_middleware import get_rag_claude_middleware

# Blueprint para rotas enhanced
enhanced_ai_bp = Blueprint('enhanced_ai', __name__)


def validate_enhanced_ai_request(func):
    """Decorador para validação de requisições AI enhanced"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            data = request.get_json()

            if not data:
                return jsonify({'error': 'Dados não fornecidos'}), 400

            # Validar prompt
            if 'prompt' not in data or not data['prompt'].strip():
                return jsonify({'error': 'Prompt é obrigatório'}), 400

            # Limitar tamanho do prompt
            if len(data['prompt']) > 15000:  # Maior limite para RAG
                return jsonify({
                    'error': 'Prompt muito longo (máximo 15.000 caracteres)'
                }), 400

            request.validated_data = data
            return func(*args, **kwargs)

        except Exception as e:
            if AUTH_AVAILABLE:
                logging_service.error(
                    "EnhancedAIRoutes",
                    "VALIDATION_ERROR",
                    f"Erro na validação: {str(e)}"
                )
            return jsonify({'error': 'Erro interno de validação'}), 500

    return wrapper


def handle_enhanced_ai_errors(func):
    """Decorador para tratamento de erros em rotas AI enhanced"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if AUTH_AVAILABLE:
                logging_service.error(
                    "EnhancedAIRoutes",
                    "ROUTE_ERROR",
                    f"Erro na rota: {str(e)}"
                )
            return jsonify({
                'error': 'Erro interno do servidor',
                'message': 'Tente novamente em alguns momentos'
            }), 500

    return wrapper


@enhanced_ai_bp.route('/chat-smart', methods=['POST'])
@require_auth if AUTH_AVAILABLE else lambda f: f
@validate_enhanced_ai_request
@handle_enhanced_ai_errors
def smart_chat_route():
    """
    Chat inteligente com RAG automático
    
    Body:
    {
        "prompt": "Pergunta para a IA",
        "use_rag": true/false (opcional, default: true),
        "use_cache": true/false (opcional, default: true),
        "rag_mode": "auto"|"force"|"disable" (opcional, default: "auto")
    }
    
    Response:
    {
        "success": true,
        "content": "Resposta da IA",
        "mode": "rag_enhanced"|"claude_only"|"cache_hit",
        "rag_sources": [...],
        "rag_chunks": 3,
        "usage": {...},
        "timestamp": "...",
        "processing_time": 1.23
    }
    """
    start_time = time.time()

    # Obter usuário atual se auth disponível
    current_user = None
    user_id = None
    if AUTH_AVAILABLE:
        current_user = auth_service.get_current_user()
        user_id = current_user.id if current_user else None

    data = request.validated_data
    prompt = data['prompt']
    use_rag = data.get('use_rag', True)
    use_cache = data.get('use_cache', True)
    rag_mode = data.get('rag_mode', 'auto')

    # Ajustar use_rag baseado no rag_mode
    if rag_mode == 'force':
        use_rag = True
    elif rag_mode == 'disable':
        use_rag = False
    # rag_mode == 'auto' mantém use_rag original

    # Rate limiting se auth disponível
    if AUTH_AVAILABLE and current_user and cache_service:
        rate_limit_key = f"enhanced_ai_rate_limit_{user_id}"
        current_requests = cache_service.get(rate_limit_key) or 0

        if current_requests >= 100:  # 100 requests por hora para RAG
            return jsonify({
                'error': 'Limite de requisições excedido',
                'retry_after': 3600,
                'limit': 100
            }), 429

        # Incrementar contador
        cache_service.set(rate_limit_key, current_requests + 1, ttl=3600)

    # Processar chat via middleware
    middleware = get_rag_claude_middleware()
    response = middleware.chat(
        prompt=prompt,
        user_id=user_id,
        use_rag=use_rag,
        use_cache=use_cache
    )

    # Adicionar tempo de processamento
    processing_time = time.time() - start_time
    response['processing_time'] = round(processing_time, 3)

    # Log da interação se disponível
    if AUTH_AVAILABLE and current_user:
        logging_service.info(
            "EnhancedAIRoutes",
            "SMART_CHAT",
            f"Smart chat processado para usuário {user_id}",
            user_id=user_id,
            metadata={
                'prompt_length': len(prompt),
                'use_rag': use_rag,
                'mode': response.get('mode', 'unknown'),
                'success': response.get('success', False),
                'processing_time': processing_time,
                'rag_chunks': response.get('rag_chunks', 0)
            }
        )

    # Determinar status code
    status_code = 200 if response.get('success', False) else 500

    return jsonify(response), status_code


@enhanced_ai_bp.route('/chat-rag', methods=['POST'])
@require_auth if AUTH_AVAILABLE else lambda f: f
@validate_enhanced_ai_request
@handle_enhanced_ai_errors
def rag_chat_route():
    """
    Chat garantindo uso do RAG (falha se RAG indisponível)
    
    Body:
    {
        "prompt": "Pergunta jurídica para RAG",
        "max_chunks": 5 (opcional),
        "similarity_threshold": 0.6 (opcional)
    }
    """
    start_time = time.time()

    # Obter usuário atual
    current_user = None
    user_id = None
    if AUTH_AVAILABLE:
        current_user = auth_service.get_current_user()
        user_id = current_user.id if current_user else None

    data = request.validated_data
    prompt = data['prompt']
    max_chunks = data.get('max_chunks', 5)
    similarity_threshold = data.get('similarity_threshold', 0.6)

    # Verificar se RAG está disponível
    middleware = get_rag_claude_middleware()
    if not middleware.rag_enabled:
        return jsonify({
            'error': 'RAG não está disponível',
            'message': 'Para usar esta funcionalidade, instale: pip install -r requirements_rag.txt',
            'fallback_available': middleware.claude_enabled
        }), 503

    # Processar com RAG obrigatório
    response = middleware.chat(
        prompt=prompt,
        user_id=user_id,
        use_rag=True,
        use_cache=True
    )

    # Se RAG falhou mas Claude disponível, informar
    if not response.get('success', False) and middleware.claude_enabled:
        response['fallback_suggestion'] = 'Use /chat-smart para fallback automático'

    # Adicionar tempo de processamento
    processing_time = time.time() - start_time
    response['processing_time'] = round(processing_time, 3)

    # Log da interação
    if AUTH_AVAILABLE and current_user:
        logging_service.info(
            "EnhancedAIRoutes",
            "RAG_CHAT",
            f"RAG chat processado para usuário {user_id}",
            user_id=user_id,
            metadata={
                'prompt_length': len(prompt),
                'max_chunks': max_chunks,
                'similarity_threshold': similarity_threshold,
                'success': response.get('success', False),
                'processing_time': processing_time
            }
        )

    status_code = 200 if response.get('success', False) else 500
    return jsonify(response), status_code


@enhanced_ai_bp.route('/chat-fallback', methods=['POST'])
@validate_enhanced_ai_request
@handle_enhanced_ai_errors
def fallback_chat_route():
    """
    Chat com fallback robusto (não requer autenticação)
    Garante sempre uma resposta válida
    
    Body:
    {
        "prompt": "Pergunta para a IA"
    }
    """
    data = request.validated_data
    prompt = data['prompt']

    # Chat com fallback garantido
    middleware = get_rag_claude_middleware()
    response = middleware.chat_with_fallback(
        prompt=prompt,
        user_id=None
    )

    return jsonify(response)


@enhanced_ai_bp.route('/status', methods=['GET'])
def enhanced_ai_status():
    """
    Status do sistema AI enhanced
    
    Response:
    {
        "claude_enabled": true,
        "rag_enabled": false,
        "cache_enabled": true,
        "components": {...},
        "rag_details": {...}
    }
    """
    middleware = get_rag_claude_middleware()
    status = middleware.get_status()

    return jsonify(status)


@enhanced_ai_bp.route('/models-info', methods=['GET'])
def models_info():
    """
    Informações sobre modelos disponíveis
    """
    info = {
        'claude': {
            'available': True,
            'model': 'claude-3-haiku-20240307',
            'capabilities': ['chat', 'document_generation', 'analysis']
        },
        'rag': {
            'available': get_rag_claude_middleware().rag_enabled,
            'embedding_model': 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
            'vector_db': 'ChromaDB',
            'capabilities': ['semantic_search', 'context_enhancement', 'document_retrieval']
        },
        'cache': {
            'available': get_rag_claude_middleware().cache_enabled,
            'type': 'Redis + Memory',
            'ttl_minutes': 30
        }
    }

    return jsonify(info)


@enhanced_ai_bp.route('/usage-tips', methods=['GET'])
def usage_tips():
    """
    Dicas de uso do sistema enhanced
    """
    middleware = get_rag_claude_middleware()

    tips = {
        'endpoints': {
            '/chat-smart': {
                'description': 'Chat inteligente com RAG automático',
                'best_for': 'Consultas gerais, RAG quando relevante',
                'fallback': 'Claude puro se RAG falhar'
            },
            '/chat-rag': {
                'description': 'Chat garantindo uso do RAG',
                'best_for': 'Consultas jurídicas específicas',
                'requires': 'RAG funcionando'
            },
            '/chat-fallback': {
                'description': 'Chat com fallback robusto',
                'best_for': 'Sistemas críticos, sem autenticação',
                'guarantee': 'Sempre retorna resposta'
            }
        },
        'system_status': {
            'rag_available': middleware.rag_enabled,
            'recommendations': []
        }
    }

    # Recomendações baseadas no status
    if not middleware.rag_enabled:
        tips['system_status']['recommendations'].append(
            'Para ativar RAG: pip install -r requirements_rag.txt'
        )

    if not middleware.cache_enabled:
        tips['system_status']['recommendations'].append(
            'Para melhor performance, configure Redis cache'
        )

    if middleware.rag_enabled and middleware.cache_enabled:
        tips['system_status']['recommendations'].append(
            'Sistema otimizado! Use /chat-smart para melhor experiência'
        )

    return jsonify(tips)


# Função de conveniência para registrar blueprint
def register_enhanced_ai_routes(app):
    """
    Registra rotas enhanced AI na aplicação Flask
    
    Args:
        app: Instância Flask
    """
    app.register_blueprint(enhanced_ai_bp, url_prefix='/api/v1/enhanced-ai')

    # Log de inicialização
    if AUTH_AVAILABLE:
        logging_service.info(
            "EnhancedAIRoutes",
            "BLUEPRINT_REGISTERED",
            "Enhanced AI routes registradas com sucesso"
        )


# Para compatibilidade com sistema existente
def get_enhanced_ai_blueprint():
    """Retorna blueprint para registro manual"""
    return enhanced_ai_bp
