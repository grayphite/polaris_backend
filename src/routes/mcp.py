"""
Rotas para Sistema MCP (Model Context Protocol)

Implementa endpoints para upload de documentos, processamento,
indexação e busca de conteúdo jurídico.
"""

import os
from functools import wraps

from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

from src.services.auth_service import auth_service, require_auth
from src.services.cache_service import cache_service
from src.services.legal_scraping_service import legal_scraping_service
from src.services.logging_service import logging_service, ActionType, log_action
from src.services.mcp_service import mcp_service
from src.services.search_service import search_service

mcp_bp = Blueprint('mcp', __name__)


def validate_file_upload(allowed_extensions=None, max_size_mb=50):
    """
    Decorador para validação de upload de arquivos
    
    Args:
        allowed_extensions: Lista de extensões permitidas
        max_size_mb: Tamanho máximo em MB
    """
    if allowed_extensions is None:
        allowed_extensions = ['pdf', 'doc', 'docx', 'txt', 'rtf']

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if 'file' not in request.files:
                    return jsonify({'error': 'Arquivo não fornecido'}), 400

                file = request.files['file']
                if file.filename == '':
                    return jsonify({'error': 'Nome do arquivo vazio'}), 400

                # Verificar extensão
                filename = secure_filename(file.filename)
                if '.' not in filename:
                    return jsonify({'error': 'Arquivo sem extensão'}), 400

                extension = filename.rsplit('.', 1)[1].lower()
                if extension not in allowed_extensions:
                    return jsonify({
                        'error': f'Extensão não permitida. Permitidas: {", ".join(allowed_extensions)}'
                    }), 400

                # Verificar tamanho (aproximado)
                file.seek(0, 2)  # Ir para o final
                size = file.tell()
                file.seek(0)  # Voltar ao início

                if size > max_size_mb * 1024 * 1024:
                    return jsonify({
                        'error': f'Arquivo muito grande. Máximo: {max_size_mb}MB'
                    }), 400

                request.validated_file = file
                request.validated_filename = filename

                return func(*args, **kwargs)

            except Exception as e:
                logging_service.error(
                    "MCPRoutes",
                    "FILE_VALIDATION_ERROR",
                    f"Erro na validação do arquivo: {str(e)}"
                )
                return jsonify({'error': 'Erro na validação do arquivo'}), 400

        return wrapper

    return decorator


def handle_mcp_errors(func):
    """Decorador para tratamento de erros específicos do MCP"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            logging_service.warning(
                "MCPRoutes",
                func.__name__.upper(),
                f"Recurso não encontrado: {str(e)}"
            )
            return jsonify({'error': 'Recurso não encontrado'}), 404
        except PermissionError as e:
            logging_service.warning(
                "MCPRoutes",
                func.__name__.upper(),
                f"Acesso negado: {str(e)}"
            )
            return jsonify({'error': 'Acesso negado'}), 403
        except ValueError as e:
            logging_service.warning(
                "MCPRoutes",
                func.__name__.upper(),
                f"Erro de validação: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            logging_service.error(
                "MCPRoutes",
                func.__name__.upper(),
                f"Erro interno: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Erro interno do sistema MCP'}), 500

    return wrapper


@mcp_bp.route('/upload', methods=['POST'])
@require_auth
@validate_file_upload()
@handle_mcp_errors
@log_action(ActionType.CREATE, "mcp_upload")
def upload_document():
    """
    Upload de documento para processamento MCP
    
    Form data:
    - file: Arquivo (PDF, DOC, DOCX, TXT, RTF)
    - category: Categoria do documento (opcional)
    - tags: Tags separadas por vírgula (opcional)
    - description: Descrição do documento (opcional)
    """
    current_user = auth_service.get_current_user()
    file = request.validated_file
    filename = request.validated_filename

    # Metadados opcionais
    category = request.form.get('category', 'general')
    tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []
    description = request.form.get('description', '')

    # Processar upload via service
    result = mcp_service.upload_document(
        file=file,
        filename=filename,
        user_id=current_user.id,
        category=category,
        tags=[tag.strip() for tag in tags if tag.strip()],
        description=description
    )

    # Log do upload
    logging_service.info(
        "MCPRoutes",
        "UPLOAD_DOCUMENT",
        f"Documento {filename} enviado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'filename': filename,
            'category': category,
            'tags': tags,
            'document_id': result.get('document_id')
        }
    )

    return jsonify(result), 201


@mcp_bp.route('/documents', methods=['GET'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_documents")
def list_documents():
    """
    Listar documentos do usuário
    
    Query parameters:
    - page: Página (default: 1)
    - per_page: Itens por página (default: 20, max: 100)
    - category: Filtrar por categoria
    - status: Filtrar por status (pending|processing|completed|failed)
    - search: Buscar por nome ou descrição
    """
    current_user = auth_service.get_current_user()

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    category = request.args.get('category')
    status = request.args.get('status')
    search = request.args.get('search', '').strip()

    # Verificar cache
    cache_key = f"mcp_documents_{current_user.id}_{page}_{per_page}_{category}_{status}_{search}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Listar documentos via service
    result = mcp_service.list_user_documents(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        category=category,
        status=status,
        search=search
    )

    # Cache por 5 minutos
    cache_service.set(cache_key, result, ttl=300)

    return jsonify(result)


@mcp_bp.route('/documents/<document_id>', methods=['GET'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_document")
def get_document(document_id: str):
    """Obter documento específico"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"mcp_document_{document_id}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter documento via service
    document = mcp_service.get_document(
        document_id=document_id,
        user_id=current_user.id
    )

    if not document:
        return jsonify({'error': 'Documento não encontrado'}), 404

    # Cache por 10 minutos
    cache_service.set(cache_key, document, ttl=600)

    return jsonify(document)


@mcp_bp.route('/documents/<document_id>', methods=['DELETE'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.DELETE, "mcp_document")
def delete_document(document_id: str):
    """Excluir documento"""
    current_user = auth_service.get_current_user()

    # Excluir via service
    success = mcp_service.delete_document(
        document_id=document_id,
        user_id=current_user.id
    )

    if not success:
        return jsonify({'error': 'Documento não encontrado'}), 404

    # Invalidar caches
    cache_service.delete(f"mcp_document_{document_id}_{current_user.id}")
    cache_pattern = f"mcp_documents_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log da exclusão
    logging_service.info(
        "MCPRoutes",
        "DELETE_DOCUMENT",
        f"Documento {document_id} excluído por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'document_id': document_id}
    )

    return jsonify({'message': 'Documento excluído com sucesso'})


@mcp_bp.route('/documents/<document_id>/download', methods=['GET'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_document_download")
def download_document(document_id: str):
    """Download do documento original"""
    current_user = auth_service.get_current_user()

    # Obter caminho do arquivo via service
    file_path = mcp_service.get_document_file_path(
        document_id=document_id,
        user_id=current_user.id
    )

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    # Log do download
    logging_service.info(
        "MCPRoutes",
        "DOWNLOAD_DOCUMENT",
        f"Documento {document_id} baixado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'document_id': document_id}
    )

    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path)
    )


@mcp_bp.route('/documents/<document_id>/reprocess', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.UPDATE, "mcp_document_reprocess")
def reprocess_document(document_id: str):
    """Reprocessar documento"""
    current_user = auth_service.get_current_user()

    # Reprocessar via service
    result = mcp_service.reprocess_document(
        document_id=document_id,
        user_id=current_user.id
    )

    if not result:
        return jsonify({'error': 'Documento não encontrado'}), 404

    # Invalidar caches
    cache_service.delete(f"mcp_document_{document_id}_{current_user.id}")
    cache_pattern = f"mcp_documents_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log do reprocessamento
    logging_service.info(
        "MCPRoutes",
        "REPROCESS_DOCUMENT",
        f"Documento {document_id} reprocessado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'document_id': document_id}
    )

    return jsonify(result)


@mcp_bp.route('/search', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_search")
def search_documents():
    """
    Busca semântica em documentos
    
    Body:
    {
        "query": "Texto da busca",
        "filters": {
            "category": "categoria",
            "tags": ["tag1", "tag2"],
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"}
        },
        "limit": 10,
        "include_content": true
    }
    """
    current_user = auth_service.get_current_user()
    data = request.get_json()

    if not data or 'query' not in data:
        return jsonify({'error': 'Query de busca é obrigatória'}), 400

    query = data['query']
    filters = data.get('filters', {})
    limit = min(data.get('limit', 10), 50)
    include_content = data.get('include_content', False)

    # Adicionar filtro de usuário
    filters['user_id'] = current_user.id

    # Buscar via service
    results = search_service.semantic_search(
        query=query,
        filters=filters,
        limit=limit,
        include_content=include_content
    )

    # Log da busca
    logging_service.info(
        "MCPRoutes",
        "SEARCH_DOCUMENTS",
        f"Busca realizada por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'query': query,
            'filters': filters,
            'results_count': len(results.get('results', []))
        }
    )

    return jsonify(results)


@mcp_bp.route('/legal-sources', methods=['GET'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_legal_sources")
def list_legal_sources():
    """Listar fontes jurídicas disponíveis"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = "mcp_legal_sources"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter fontes via service
    sources = legal_scraping_service.get_available_sources()

    # Cache por 1 hora
    cache_service.set(cache_key, sources, ttl=3600)

    return jsonify(sources)


@mcp_bp.route('/legal-sources/<source_id>/scrape', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.CREATE, "mcp_legal_scrape")
def scrape_legal_source(source_id: str):
    """Executar scraping de fonte jurídica específica"""
    current_user = auth_service.get_current_user()

    # Verificar se usuário tem permissão (apenas admins)
    if not current_user.is_admin:
        return jsonify({'error': 'Acesso negado'}), 403

    # Executar scraping via service
    result = legal_scraping_service.scrape_source(source_id)

    # Log do scraping
    logging_service.info(
        "MCPRoutes",
        "SCRAPE_LEGAL_SOURCE",
        f"Scraping de {source_id} executado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'source_id': source_id,
            'documents_found': result.get('documents_found', 0)
        }
    )

    return jsonify(result)


@mcp_bp.route('/legal-sources/scrape-all', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.CREATE, "mcp_legal_scrape_all")
def scrape_all_legal_sources():
    """Executar scraping de todas as fontes jurídicas"""
    current_user = auth_service.get_current_user()

    # Verificar se usuário tem permissão (apenas admins)
    if not current_user.is_admin:
        return jsonify({'error': 'Acesso negado'}), 403

    # Executar scraping via service
    result = legal_scraping_service.scrape_all_sources()

    # Log do scraping
    logging_service.info(
        "MCPRoutes",
        "SCRAPE_ALL_SOURCES",
        f"Scraping completo executado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'sources_processed': result.get('sources_processed', 0),
            'total_documents': result.get('total_documents', 0)
        }
    )

    return jsonify(result)


@mcp_bp.route('/index/rebuild', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.UPDATE, "mcp_index_rebuild")
def rebuild_search_index():
    """Reconstruir índice de busca"""
    current_user = auth_service.get_current_user()

    # Verificar se usuário tem permissão (apenas admins)
    if not current_user.is_admin:
        return jsonify({'error': 'Acesso negado'}), 403

    # Reconstruir índice via service
    result = search_service.rebuild_index()

    # Invalidar todos os caches de busca
    cache_service.clear("mcp_search_*")
    cache_service.clear("mcp_documents_*")

    # Log da reconstrução
    logging_service.info(
        "MCPRoutes",
        "REBUILD_INDEX",
        f"Índice reconstruído por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'documents_indexed': result.get('documents_indexed', 0),
            'index_size_mb': result.get('index_size_mb', 0)
        }
    )

    return jsonify(result)


@mcp_bp.route('/statistics', methods=['GET'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.READ, "mcp_statistics")
def get_mcp_statistics():
    """Obter estatísticas do sistema MCP"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"mcp_statistics_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter estatísticas via service
    stats = mcp_service.get_statistics(current_user.id)

    # Cache por 15 minutos
    cache_service.set(cache_key, stats, ttl=900)

    return jsonify(stats)


@mcp_bp.route('/health', methods=['GET'])
def health_check():
    """Health check do sistema MCP"""
    try:
        # Verificar services
        mcp_health = mcp_service.health_check()
        search_health = search_service.health_check()
        scraping_health = legal_scraping_service.health_check()

        overall_status = "healthy"
        if any(h.get('status') != 'healthy' for h in [mcp_health, search_health, scraping_health]):
            overall_status = "degraded"

        return jsonify({
            'status': overall_status,
            'service': 'mcp',
            'components': {
                'mcp_service': mcp_health,
                'search_service': search_health,
                'scraping_service': scraping_health
            }
        })

    except Exception as e:
        logging_service.error(
            "MCPRoutes",
            "HEALTH_CHECK_ERROR",
            f"Erro no health check: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'mcp',
            'error': str(e)
        }), 500


@mcp_bp.route('/categories', methods=['GET'])
@require_auth
@handle_mcp_errors
def get_document_categories():
    """Listar categorias de documentos disponíveis"""
    # Verificar cache
    cache_key = "mcp_document_categories"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter categorias via service
    categories = mcp_service.get_document_categories()

    # Cache por 1 hora
    cache_service.set(cache_key, categories, ttl=3600)

    return jsonify(categories)


@mcp_bp.route('/bulk-upload', methods=['POST'])
@require_auth
@handle_mcp_errors
@log_action(ActionType.CREATE, "mcp_bulk_upload")
def bulk_upload_documents():
    """Upload em lote de documentos"""
    current_user = auth_service.get_current_user()

    if 'files' not in request.files:
        return jsonify({'error': 'Arquivos não fornecidos'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'Lista de arquivos vazia'}), 400

    # Limitar número de arquivos
    if len(files) > 20:
        return jsonify({'error': 'Máximo 20 arquivos por upload'}), 400

    # Metadados opcionais
    category = request.form.get('category', 'general')
    tags = request.form.get('tags', '').split(',') if request.form.get('tags') else []

    # Processar upload em lote via service
    result = mcp_service.bulk_upload_documents(
        files=files,
        user_id=current_user.id,
        category=category,
        tags=[tag.strip() for tag in tags if tag.strip()]
    )

    # Log do upload em lote
    logging_service.info(
        "MCPRoutes",
        "BULK_UPLOAD",
        f"Upload em lote de {len(files)} arquivos por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'files_count': len(files),
            'category': category,
            'tags': tags,
            'successful_uploads': result.get('successful_uploads', 0),
            'failed_uploads': result.get('failed_uploads', 0)
        }
    )

    return jsonify(result)
