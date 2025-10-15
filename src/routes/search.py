"""
Rotas para Sistema de Busca Semântica

Implementa endpoints para busca avançada, indexação
e análise de conteúdo jurídico.
"""

from functools import wraps

from flask import Blueprint, request, jsonify

from src.services.auth_service import auth_service, require_auth
from src.services.cache_service import cache_service
from src.services.logging_service import logging_service, ActionType, log_action
from src.services.search_service import search_service

search_bp = Blueprint('search', __name__)


def validate_search_request(func):
    """Decorador para validação de requisições de busca"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            data = request.get_json() if request.method == 'POST' else {}

            # Para GET, usar query parameters
            if request.method == 'GET':
                query = request.args.get('q', '').strip()
                if not query:
                    return jsonify({'error': 'Parâmetro de busca "q" é obrigatório'}), 400

                request.search_query = query
                request.search_filters = {
                    'category': request.args.get('category'),
                    'tags': request.args.getlist('tags'),
                    'date_from': request.args.get('date_from'),
                    'date_to': request.args.get('date_to'),
                    'source': request.args.get('source')
                }
                request.search_limit = min(int(request.args.get('limit', 10)), 50)

            # Para POST, usar body
            else:
                if not data or 'query' not in data:
                    return jsonify({'error': 'Query de busca é obrigatória'}), 400

                query = data['query'].strip()
                if not query:
                    return jsonify({'error': 'Query de busca não pode estar vazia'}), 400

                request.search_query = query
                request.search_filters = data.get('filters', {})
                request.search_limit = min(data.get('limit', 10), 50)

            # Validar tamanho da query
            if len(request.search_query) > 1000:
                return jsonify({'error': 'Query muito longa (máximo 1000 caracteres)'}), 400

            return func(*args, **kwargs)

        except Exception as e:
            logging_service.error(
                "SearchRoutes",
                "VALIDATION_ERROR",
                f"Erro na validação: {str(e)}"
            )
            return jsonify({'error': 'Erro na validação da busca'}), 400

    return wrapper


def handle_search_errors(func):
    """Decorador para tratamento de erros específicos de busca"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ConnectionError as e:
            logging_service.error(
                "SearchRoutes",
                func.__name__.upper(),
                f"Erro de conexão com índice de busca: {str(e)}"
            )
            return jsonify({
                'error': 'Serviço de busca temporariamente indisponível',
                'retry_after': 30
            }), 503
        except ValueError as e:
            logging_service.warning(
                "SearchRoutes",
                func.__name__.upper(),
                f"Erro de validação: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logging_service.error(
                "SearchRoutes",
                func.__name__.upper(),
                f"Erro interno: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Erro interno do serviço de busca'}), 500

    return wrapper


@search_bp.route('/semantic', methods=['GET', 'POST'])
@require_auth
@validate_search_request
@handle_search_errors
@log_action(ActionType.READ, "semantic_search")
def semantic_search():
    """
    Busca semântica em documentos
    
    GET /search/semantic?q=query&category=cat&limit=10
    POST /search/semantic
    {
        "query": "texto da busca",
        "filters": {
            "category": "categoria",
            "tags": ["tag1", "tag2"],
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "source": "fonte"
        },
        "limit": 10,
        "include_content": true,
        "similarity_threshold": 0.7
    }
    """
    current_user = auth_service.get_current_user()

    query = request.search_query
    filters = request.search_filters.copy()
    limit = request.search_limit

    # Parâmetros adicionais para POST
    include_content = False
    similarity_threshold = 0.5

    if request.method == 'POST':
        data = request.get_json()
        include_content = data.get('include_content', False)
        similarity_threshold = data.get('similarity_threshold', 0.5)

    # Adicionar filtro de usuário
    filters['user_id'] = current_user.id

    # Verificar cache
    cache_key = f"semantic_search_{hash(query)}_{hash(str(filters))}_{limit}_{include_content}_{similarity_threshold}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        logging_service.debug(
            "SearchRoutes",
            "SEMANTIC_SEARCH_CACHED",
            f"Resultado obtido do cache para usuário {current_user.id}"
        )
        return jsonify(cached_result)

    # Executar busca via service
    results = search_service.semantic_search(
        query=query,
        filters=filters,
        limit=limit,
        include_content=include_content,
        similarity_threshold=similarity_threshold
    )

    # Cache por 10 minutos
    cache_service.set(cache_key, results, ttl=600)

    # Log da busca
    logging_service.info(
        "SearchRoutes",
        "SEMANTIC_SEARCH",
        f"Busca semântica realizada por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'query': query,
            'filters': filters,
            'results_count': len(results.get('results', [])),
            'search_time_ms': results.get('search_time_ms', 0)
        }
    )

    return jsonify(results)


@search_bp.route('/keyword', methods=['GET', 'POST'])
@require_auth
@validate_search_request
@handle_search_errors
@log_action(ActionType.READ, "keyword_search")
def keyword_search():
    """
    Busca por palavras-chave (tradicional)
    
    Similar à busca semântica, mas usa correspondência exata de termos
    """
    current_user = auth_service.get_current_user()

    query = request.search_query
    filters = request.search_filters.copy()
    limit = request.search_limit

    # Adicionar filtro de usuário
    filters['user_id'] = current_user.id

    # Verificar cache
    cache_key = f"keyword_search_{hash(query)}_{hash(str(filters))}_{limit}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Executar busca via service
    results = search_service.keyword_search(
        query=query,
        filters=filters,
        limit=limit
    )

    # Cache por 15 minutos
    cache_service.set(cache_key, results, ttl=900)

    # Log da busca
    logging_service.info(
        "SearchRoutes",
        "KEYWORD_SEARCH",
        f"Busca por palavras-chave realizada por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'query': query,
            'filters': filters,
            'results_count': len(results.get('results', []))
        }
    )

    return jsonify(results)


@search_bp.route('/suggestions', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "search_suggestions")
def get_search_suggestions():
    """
    Obter sugestões de busca baseadas em query parcial
    
    GET /search/suggestions?q=partial_query&limit=5
    """
    current_user = auth_service.get_current_user()

    partial_query = request.args.get('q', '').strip()
    if not partial_query:
        return jsonify({'suggestions': []})

    if len(partial_query) < 2:
        return jsonify({'suggestions': []})

    limit = min(int(request.args.get('limit', 5)), 20)

    # Verificar cache
    cache_key = f"search_suggestions_{hash(partial_query)}_{limit}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter sugestões via service
    suggestions = search_service.get_search_suggestions(
        partial_query=partial_query,
        user_id=current_user.id,
        limit=limit
    )

    # Cache por 1 hora
    cache_service.set(cache_key, suggestions, ttl=3600)

    return jsonify(suggestions)


@search_bp.route('/similar/<document_id>', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "similar_documents")
def find_similar_documents(document_id: str):
    """
    Encontrar documentos similares a um documento específico
    
    GET /search/similar/doc123?limit=5&threshold=0.7
    """
    current_user = auth_service.get_current_user()

    limit = min(int(request.args.get('limit', 5)), 20)
    threshold = float(request.args.get('threshold', 0.7))

    # Verificar cache
    cache_key = f"similar_docs_{document_id}_{limit}_{threshold}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Encontrar documentos similares via service
    similar_docs = search_service.find_similar_documents(
        document_id=document_id,
        user_id=current_user.id,
        limit=limit,
        similarity_threshold=threshold
    )

    # Cache por 30 minutos
    cache_service.set(cache_key, similar_docs, ttl=1800)

    # Log da busca
    logging_service.info(
        "SearchRoutes",
        "SIMILAR_DOCUMENTS",
        f"Busca por documentos similares realizada por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'document_id': document_id,
            'limit': limit,
            'threshold': threshold,
            'results_count': len(similar_docs.get('results', []))
        }
    )

    return jsonify(similar_docs)


@search_bp.route('/facets', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "search_facets")
def get_search_facets():
    """
    Obter facetas (filtros) disponíveis para busca
    
    GET /search/facets?q=optional_query
    """
    current_user = auth_service.get_current_user()

    query = request.args.get('q', '').strip()

    # Verificar cache
    cache_key = f"search_facets_{hash(query)}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter facetas via service
    facets = search_service.get_search_facets(
        query=query if query else None,
        user_id=current_user.id
    )

    # Cache por 1 hora
    cache_service.set(cache_key, facets, ttl=3600)

    return jsonify(facets)


@search_bp.route('/trending', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "trending_searches")
def get_trending_searches():
    """
    Obter buscas em tendência
    
    GET /search/trending?period=week&limit=10
    """
    current_user = auth_service.get_current_user()

    period = request.args.get('period', 'week')  # day, week, month
    limit = min(int(request.args.get('limit', 10)), 50)

    # Validar período
    valid_periods = ['day', 'week', 'month']
    if period not in valid_periods:
        return jsonify({
            'error': f'Período inválido. Períodos válidos: {", ".join(valid_periods)}'
        }), 400

    # Verificar cache
    cache_key = f"trending_searches_{period}_{limit}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter buscas em tendência via service
    trending = search_service.get_trending_searches(
        period=period,
        user_id=current_user.id,
        limit=limit
    )

    # Cache por 1 hora
    cache_service.set(cache_key, trending, ttl=3600)

    return jsonify(trending)


@search_bp.route('/history', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "search_history")
def get_search_history():
    """
    Obter histórico de buscas do usuário
    
    GET /search/history?limit=20&page=1
    """
    current_user = auth_service.get_current_user()

    page = request.args.get('page', 1, type=int)
    limit = min(int(request.args.get('limit', 20)), 100)

    # Verificar cache
    cache_key = f"search_history_{current_user.id}_{page}_{limit}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter histórico via service
    history = search_service.get_user_search_history(
        user_id=current_user.id,
        page=page,
        limit=limit
    )

    # Cache por 5 minutos
    cache_service.set(cache_key, history, ttl=300)

    return jsonify(history)


@search_bp.route('/history/<search_id>', methods=['DELETE'])
@require_auth
@handle_search_errors
@log_action(ActionType.DELETE, "search_history_item")
def delete_search_history_item(search_id: str):
    """Excluir item do histórico de busca"""
    current_user = auth_service.get_current_user()

    # Excluir via service
    success = search_service.delete_search_history_item(
        search_id=search_id,
        user_id=current_user.id
    )

    if not success:
        return jsonify({'error': 'Item do histórico não encontrado'}), 404

    # Invalidar cache do histórico
    cache_pattern = f"search_history_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log da exclusão
    logging_service.info(
        "SearchRoutes",
        "DELETE_HISTORY_ITEM",
        f"Item do histórico {search_id} excluído por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'search_id': search_id}
    )

    return jsonify({'message': 'Item do histórico excluído com sucesso'})


@search_bp.route('/export', methods=['POST'])
@require_auth
@handle_search_errors
@log_action(ActionType.CREATE, "search_export")
def export_search_results():
    """
    Exportar resultados de busca
    
    POST /search/export
    {
        "query": "busca",
        "filters": {...},
        "format": "csv|json|excel",
        "include_content": true
    }
    """
    current_user = auth_service.get_current_user()
    data = request.get_json()

    if not data or 'query' not in data:
        return jsonify({'error': 'Query de busca é obrigatória'}), 400

    query = data['query']
    filters = data.get('filters', {})
    format_type = data.get('format', 'csv')
    include_content = data.get('include_content', False)

    # Validar formato
    valid_formats = ['csv', 'json', 'excel']
    if format_type not in valid_formats:
        return jsonify({
            'error': f'Formato inválido. Formatos válidos: {", ".join(valid_formats)}'
        }), 400

    # Adicionar filtro de usuário
    filters['user_id'] = current_user.id

    # Exportar via service
    export_result = search_service.export_search_results(
        query=query,
        filters=filters,
        format_type=format_type,
        include_content=include_content,
        user_id=current_user.id
    )

    # Log da exportação
    logging_service.info(
        "SearchRoutes",
        "EXPORT_RESULTS",
        f"Resultados exportados por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'query': query,
            'format': format_type,
            'results_count': export_result.get('results_count', 0)
        }
    )

    return jsonify(export_result)


@search_bp.route('/analytics', methods=['GET'])
@require_auth
@handle_search_errors
@log_action(ActionType.READ, "search_analytics")
def get_search_analytics():
    """
    Obter analytics de busca do usuário
    
    GET /search/analytics?period=month
    """
    current_user = auth_service.get_current_user()

    period = request.args.get('period', 'month')  # day, week, month, year

    # Validar período
    valid_periods = ['day', 'week', 'month', 'year']
    if period not in valid_periods:
        return jsonify({
            'error': f'Período inválido. Períodos válidos: {", ".join(valid_periods)}'
        }), 400

    # Verificar cache
    cache_key = f"search_analytics_{current_user.id}_{period}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter analytics via service
    analytics = search_service.get_user_search_analytics(
        user_id=current_user.id,
        period=period
    )

    # Cache por 1 hora
    cache_service.set(cache_key, analytics, ttl=3600)

    return jsonify(analytics)


@search_bp.route('/index/status', methods=['GET'])
@require_auth
@handle_search_errors
def get_index_status():
    """Obter status do índice de busca"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = "search_index_status"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter status via service
    status = search_service.get_index_status()

    # Cache por 5 minutos
    cache_service.set(cache_key, status, ttl=300)

    return jsonify(status)


@search_bp.route('/health', methods=['GET'])
def health_check():
    """Health check do serviço de busca"""
    try:
        # Verificar service
        health_status = search_service.health_check()

        return jsonify({
            'status': 'healthy',
            'service': 'search',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })

    except Exception as e:
        logging_service.error(
            "SearchRoutes",
            "HEALTH_CHECK_ERROR",
            f"Erro no health check: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'search',
            'error': str(e)
        }), 500
