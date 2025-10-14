"""
Rotas para Claude AI e Geração de Documentos

Implementa endpoints para chat com IA, geração de documentos
e funcionalidades relacionadas ao Claude AI.
"""

import os
from functools import wraps

from flask import Blueprint, request, jsonify, send_file

from src.services.auth_service import auth_service, require_auth
from src.services.cache_service import cache_service
from src.services.claude_ai_service import claude_ai_service
from src.services.logging_service import logging_service, ActionType, log_action

ai_bp = Blueprint('ai', __name__)


def validate_ai_request(func):
    """Decorador para validação de requisições de IA"""

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
            if len(data['prompt']) > 10000:
                return jsonify({'error': 'Prompt muito longo (máximo 10.000 caracteres)'}), 400

            request.validated_data = data
            return func(*args, **kwargs)

        except Exception as e:
            logging_service.error(
                "AIRoutes",
                "VALIDATION_ERROR",
                f"Erro na validação: {str(e)}"
            )
            return jsonify({'error': 'Erro na validação dos dados'}), 400

    return wrapper


def handle_ai_errors(func):
    """Decorador para tratamento de erros específicos de IA"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConnectionError as e:
            logging_service.error(
                "AIRoutes",
                func.__name__.upper(),
                f"Erro de conexão com Claude AI: {str(e)}"
            )
            return jsonify({
                'error': 'Serviço de IA temporariamente indisponível',
                'retry_after': 30
            }), 503
        except ValueError as e:
            logging_service.warning(
                "AIRoutes",
                func.__name__.upper(),
                f"Erro de validação: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logging_service.error(
                "AIRoutes",
                func.__name__.upper(),
                f"Erro interno: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Erro interno do serviço de IA'}), 500

    return wrapper


@ai_bp.route('/chat', methods=['POST'])
@require_auth
@validate_ai_request
@handle_ai_errors
@log_action(ActionType.CREATE, "ai_chat")
def chat_with_ai():
    """
    Chat com Claude AI
    
    Body:
    {
        "prompt": "Pergunta para a IA",
        "context": "Contexto adicional (opcional)",
        "use_rag": true/false,
        "conversation_id": "ID da conversa (opcional)"
    }
    """
    current_user = auth_service.get_current_user()
    data = request.validated_data

    prompt = data['prompt']
    context = data.get('context', '')
    use_rag = data.get('use_rag', True)
    conversation_id = data.get('conversation_id')

    # Verificar rate limiting
    rate_limit_key = f"ai_chat_rate_limit_{current_user.id}"
    current_requests = cache_service.get(rate_limit_key) or 0

    if current_requests >= 50:  # 50 requests por hora
        return jsonify({
            'error': 'Limite de requisições excedido',
            'retry_after': 3600
        }), 429

    # Incrementar contador de rate limiting
    cache_service.set(rate_limit_key, current_requests + 1, ttl=3600)

    # Processar chat via service
    response = claude_ai_service.chat(
        prompt=prompt,
        context=context,
        user_id=current_user.id,
        use_rag=use_rag,
        conversation_id=conversation_id
    )

    # Log da interação
    logging_service.info(
        "AIRoutes",
        "CHAT_AI",
        f"Chat processado para usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'prompt_length': len(prompt),
            'use_rag': use_rag,
            'conversation_id': conversation_id,
            'response_length': len(response.get('response', ''))
        }
    )

    return jsonify(response)


@ai_bp.route('/generate-document', methods=['POST'])
@require_auth
@validate_ai_request
@handle_ai_errors
@log_action(ActionType.CREATE, "ai_document")
def generate_document():
    """
    Gerar documento com Claude AI
    
    Body:
    {
        "prompt": "Instruções para o documento",
        "document_type": "trust_agreement|will|contract|memo",
        "client_data": {...},
        "template_id": "ID do template (opcional)",
        "format": "pdf|docx|html"
    }
    """
    current_user = auth_service.get_current_user()
    data = request.validated_data

    prompt = data['prompt']
    document_type = data.get('document_type', 'memo')
    client_data = data.get('client_data', {})
    template_id = data.get('template_id')
    format_type = data.get('format', 'pdf')

    # Validar tipo de documento
    valid_types = ['trust_agreement', 'will', 'contract', 'memo', 'legal_opinion']
    if document_type not in valid_types:
        return jsonify({
            'error': f'Tipo de documento inválido. Tipos válidos: {", ".join(valid_types)}'
        }), 400

    # Validar formato
    valid_formats = ['pdf', 'docx', 'html']
    if format_type not in valid_formats:
        return jsonify({
            'error': f'Formato inválido. Formatos válidos: {", ".join(valid_formats)}'
        }), 400

    # Gerar documento via service
    result = claude_ai_service.generate_document(
        prompt=prompt,
        document_type=document_type,
        client_data=client_data,
        user_id=current_user.id,
        template_id=template_id,
        format_type=format_type
    )

    # Log da geração
    logging_service.info(
        "AIRoutes",
        "GENERATE_DOCUMENT",
        f"Documento gerado para usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'document_type': document_type,
            'format': format_type,
            'template_id': template_id,
            'document_id': result.get('document_id')
        }
    )

    return jsonify(result)


@ai_bp.route('/documents/<document_id>/download', methods=['GET'])
@require_auth
@handle_ai_errors
@log_action(ActionType.READ, "ai_document_download")
def download_document(document_id: str):
    """Download de documento gerado"""
    current_user = auth_service.get_current_user()

    # Obter documento via service
    file_path = claude_ai_service.get_document_file(
        document_id=document_id,
        user_id=current_user.id
    )

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Documento não encontrado'}), 404

    # Log do download
    logging_service.info(
        "AIRoutes",
        "DOWNLOAD_DOCUMENT",
        f"Documento {document_id} baixado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'document_id': document_id}
    )

    return send_file(
        file_path,
        as_attachment=True,
        download_name=f"document_{document_id}.pdf"
    )


@ai_bp.route('/conversations', methods=['GET'])
@require_auth
@handle_ai_errors
@log_action(ActionType.READ, "ai_conversations")
def get_conversations():
    """Listar conversas do usuário"""
    current_user = auth_service.get_current_user()

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    # Verificar cache
    cache_key = f"ai_conversations_{current_user.id}_{page}_{per_page}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter conversas via service
    conversations = claude_ai_service.get_user_conversations(
        user_id=current_user.id,
        page=page,
        per_page=per_page
    )

    # Cache por 5 minutos
    cache_service.set(cache_key, conversations, ttl=300)

    return jsonify(conversations)


@ai_bp.route('/conversations/<conversation_id>', methods=['GET'])
@require_auth
@handle_ai_errors
@log_action(ActionType.READ, "ai_conversation")
def get_conversation(conversation_id: str):
    """Obter conversa específica"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"ai_conversation_{conversation_id}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter conversa via service
    conversation = claude_ai_service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id
    )

    if not conversation:
        return jsonify({'error': 'Conversa não encontrada'}), 404

    # Cache por 10 minutos
    cache_service.set(cache_key, conversation, ttl=600)

    return jsonify(conversation)


@ai_bp.route('/conversations/<conversation_id>', methods=['DELETE'])
@require_auth
@handle_ai_errors
@log_action(ActionType.DELETE, "ai_conversation")
def delete_conversation(conversation_id: str):
    """Excluir conversa"""
    current_user = auth_service.get_current_user()

    # Excluir via service
    success = claude_ai_service.delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user.id
    )

    if not success:
        return jsonify({'error': 'Conversa não encontrada'}), 404

    # Invalidar cache
    cache_service.delete(f"ai_conversation_{conversation_id}_{current_user.id}")
    cache_pattern = f"ai_conversations_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log da exclusão
    logging_service.info(
        "AIRoutes",
        "DELETE_CONVERSATION",
        f"Conversa {conversation_id} excluída por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'conversation_id': conversation_id}
    )

    return jsonify({'message': 'Conversa excluída com sucesso'})


@ai_bp.route('/templates', methods=['GET'])
@require_auth
@handle_ai_errors
@log_action(ActionType.READ, "ai_templates")
def get_document_templates():
    """Listar templates de documentos"""
    current_user = auth_service.get_current_user()

    document_type = request.args.get('document_type')

    # Verificar cache
    cache_key = f"ai_templates_{document_type or 'all'}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter templates via service
    templates = claude_ai_service.get_document_templates(
        document_type=document_type
    )

    # Cache por 1 hora
    cache_service.set(cache_key, templates, ttl=3600)

    return jsonify(templates)


@ai_bp.route('/analyze-document', methods=['POST'])
@require_auth
@handle_ai_errors
@log_action(ActionType.CREATE, "ai_document_analysis")
def analyze_document():
    """
    Analisar documento com Claude AI
    
    Body:
    {
        "document_text": "Texto do documento",
        "analysis_type": "legal_review|risk_assessment|compliance_check",
        "focus_areas": ["tax", "compliance", "structure"]
    }
    """
    current_user = auth_service.get_current_user()
    data = request.get_json()

    if not data or 'document_text' not in data:
        return jsonify({'error': 'Texto do documento é obrigatório'}), 400

    document_text = data['document_text']
    analysis_type = data.get('analysis_type', 'legal_review')
    focus_areas = data.get('focus_areas', [])

    # Validar tipo de análise
    valid_types = ['legal_review', 'risk_assessment', 'compliance_check', 'tax_analysis']
    if analysis_type not in valid_types:
        return jsonify({
            'error': f'Tipo de análise inválido. Tipos válidos: {", ".join(valid_types)}'
        }), 400

    # Analisar documento via service
    analysis = claude_ai_service.analyze_document(
        document_text=document_text,
        analysis_type=analysis_type,
        focus_areas=focus_areas,
        user_id=current_user.id
    )

    # Log da análise
    logging_service.info(
        "AIRoutes",
        "ANALYZE_DOCUMENT",
        f"Documento analisado para usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'analysis_type': analysis_type,
            'focus_areas': focus_areas,
            'document_length': len(document_text)
        }
    )

    return jsonify(analysis)


@ai_bp.route('/suggestions', methods=['POST'])
@require_auth
@handle_ai_errors
@log_action(ActionType.CREATE, "ai_suggestions")
def get_ai_suggestions():
    """
    Obter sugestões da IA baseadas em contexto
    
    Body:
    {
        "context": "Contexto do cliente",
        "suggestion_type": "structure|jurisdiction|tax_strategy",
        "client_profile": {...}
    }
    """
    current_user = auth_service.get_current_user()
    data = request.get_json()

    if not data or 'context' not in data:
        return jsonify({'error': 'Contexto é obrigatório'}), 400

    context = data['context']
    suggestion_type = data.get('suggestion_type', 'structure')
    client_profile = data.get('client_profile', {})

    # Obter sugestões via service
    suggestions = claude_ai_service.get_suggestions(
        context=context,
        suggestion_type=suggestion_type,
        client_profile=client_profile,
        user_id=current_user.id
    )

    # Log das sugestões
    logging_service.info(
        "AIRoutes",
        "GET_SUGGESTIONS",
        f"Sugestões geradas para usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'suggestion_type': suggestion_type,
            'context_length': len(context)
        }
    )

    return jsonify(suggestions)


@ai_bp.route('/health', methods=['GET'])
def health_check():
    """Health check do serviço de IA"""
    try:
        # Verificar service
        health_status = claude_ai_service.health_check()

        return jsonify({
            'status': 'healthy',
            'service': 'claude_ai',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })

    except Exception as e:
        logging_service.error(
            "AIRoutes",
            "HEALTH_CHECK_ERROR",
            f"Erro no health check: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'claude_ai',
            'error': str(e)
        }), 500


@ai_bp.route('/usage-stats', methods=['GET'])
@require_auth
@handle_ai_errors
@log_action(ActionType.READ, "ai_usage_stats")
def get_usage_stats():
    """Obter estatísticas de uso da IA"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"ai_usage_stats_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter estatísticas via service
    stats = claude_ai_service.get_usage_statistics(current_user.id)

    # Cache por 15 minutos
    cache_service.set(cache_key, stats, ttl=900)

    return jsonify(stats)
