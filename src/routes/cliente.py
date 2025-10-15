"""
Rotas refatoradas para Cliente usando Services

Esta versão refatorada usa o ClienteService para lógica de negócio,
decoradores para logging/auth e validação centralizada.
"""

from functools import wraps

from flask import Blueprint, request, jsonify

from src.services.auth_service import auth_service, require_auth
from src.services.cache_service import cache_service
from src.services.cliente_service import cliente_service
from src.services.logging_service import logging_service, ActionType, log_action

cliente_bp = Blueprint('cliente', __name__)


def validate_request_data(required_fields: list = None, optional_fields: list = None):
    """
    Decorador para validação de dados da requisição
    
    Args:
        required_fields: Lista de campos obrigatórios
        optional_fields: Lista de campos opcionais permitidos
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json() if request.method in ['POST', 'PUT'] else {}

                # Validar campos obrigatórios
                if required_fields:
                    for field in required_fields:
                        if field not in data or not data[field]:
                            return jsonify({
                                'error': f'Campo {field} é obrigatório',
                                'field': field
                            }), 400

                # Filtrar apenas campos permitidos
                if optional_fields:
                    allowed_fields = (required_fields or []) + optional_fields
                    filtered_data = {k: v for k, v in data.items() if k in allowed_fields}
                    request.validated_data = filtered_data
                else:
                    request.validated_data = data

                return func(*args, **kwargs)

            except Exception as e:
                logging_service.error(
                    "ClienteRoutes",
                    "VALIDATION_ERROR",
                    f"Erro na validação: {str(e)}",
                    error_details={'error': str(e)}
                )
                return jsonify({'error': 'Erro na validação dos dados'}), 400

        return wrapper

    return decorator


def handle_errors(func):
    """Decorador para tratamento centralizado de erros"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            logging_service.warning(
                "ClienteRoutes",
                func.__name__.upper(),
                f"Erro de validação: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "ClienteRoutes",
                func.__name__.upper(),
                f"Erro de permissão: {str(e)}"
            )
            return jsonify({'error': 'Acesso negado'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "ClienteRoutes",
                func.__name__.upper(),
                f"Recurso não encontrado: {str(e)}"
            )
            return jsonify({'error': 'Recurso não encontrado'}), 404
        except Exception as e:
            logging_service.error(
                "ClienteRoutes",
                func.__name__.upper(),
                f"Erro interno: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Erro interno do servidor'}), 500

    return wrapper


@cliente_bp.route('/clientes', methods=['GET'])
@require_auth
@handle_errors
@log_action(ActionType.READ, "cliente")
def get_clientes():
    """
    Listar clientes com paginação e busca
    
    Query parameters:
    - page: número da página (default: 1)
    - per_page: itens por página (default: 10, max: 100)
    - search: busca por nome ou email
    """
    # Obter usuário autenticado
    current_user = auth_service.get_current_user()

    # Parâmetros de consulta
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()

    # Verificar cache
    cache_key = f"clientes_list_{current_user.id}_{page}_{per_page}_{search}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        logging_service.debug(
            "ClienteRoutes",
            "GET_CLIENTES_CACHED",
            f"Resultado obtido do cache para usuário {current_user.id}"
        )
        return jsonify(cached_result)

    # Buscar clientes via service
    result = cliente_service.list_clientes(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        search=search
    )

    # Cache por 5 minutos
    cache_service.set(cache_key, result, ttl=300)

    logging_service.info(
        "ClienteRoutes",
        "GET_CLIENTES",
        f"Listagem de clientes para usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'page': page,
            'per_page': per_page,
            'search': search,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )

    return jsonify(result)


@cliente_bp.route('/clientes/<int:cliente_id>', methods=['GET'])
@require_auth
@handle_errors
@log_action(ActionType.READ, "cliente")
def get_cliente(cliente_id: int):
    """Obter cliente específico por ID"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"cliente_{cliente_id}_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Buscar cliente via service
    cliente = cliente_service.get_cliente_by_id(
        cliente_id=cliente_id,
        user_id=current_user.id
    )

    if not cliente:
        raise FileNotFoundError("Cliente não encontrado")

    # Cache por 10 minutos
    cache_service.set(cache_key, cliente, ttl=600)

    logging_service.info(
        "ClienteRoutes",
        "GET_CLIENTE",
        f"Cliente {cliente_id} acessado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'cliente_id': cliente_id}
    )

    return jsonify(cliente)


@cliente_bp.route('/clientes', methods=['POST'])
@require_auth
@validate_request_data(
    required_fields=['nome_completo', 'email'],
    optional_fields=[
        'telefone', 'nacionalidade', 'cpf', 'passaporte', 'rg',
        'data_nascimento', 'endereco_completo', 'cidade', 'estado',
        'cep', 'pais', 'profissao', 'empresa', 'cargo', 'renda_anual',
        'patrimonio_total', 'origem_patrimonio', 'residente_fiscal_brasil',
        'residente_fiscal_eua', 'outros_paises_residencia', 'objetivos_planejamento',
        'tolerancia_risco', 'horizonte_investimento', 'possui_offshore',
        'detalhes_offshore', 'possui_trust', 'detalhes_trust'
    ]
)
@handle_errors
@log_action(ActionType.CREATE, "cliente")
def create_cliente():
    """Criar novo cliente"""
    current_user = auth_service.get_current_user()
    data = request.validated_data

    # Adicionar user_id aos dados
    data['user_id'] = current_user.id

    # Criar cliente via service
    cliente = cliente_service.create_cliente(data)

    # Invalidar cache de listagem
    cache_pattern = f"clientes_list_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log de auditoria
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="cliente",
        resource_id=str(cliente['id']),
        new_values=cliente,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'cliente_nome': cliente['nome_completo']}
    )

    logging_service.info(
        "ClienteRoutes",
        "CREATE_CLIENTE",
        f"Cliente criado: {cliente['nome_completo']} por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'cliente_id': cliente['id'], 'cliente_nome': cliente['nome_completo']}
    )

    return jsonify(cliente), 201


@cliente_bp.route('/clientes/<int:cliente_id>', methods=['PUT'])
@require_auth
@validate_request_data(
    optional_fields=[
        'nome_completo', 'email', 'telefone', 'nacionalidade', 'cpf',
        'passaporte', 'rg', 'data_nascimento', 'endereco_completo', 'cidade',
        'estado', 'cep', 'pais', 'profissao', 'empresa', 'cargo', 'renda_anual',
        'patrimonio_total', 'origem_patrimonio', 'residente_fiscal_brasil',
        'residente_fiscal_eua', 'outros_paises_residencia', 'objetivos_planejamento',
        'tolerancia_risco', 'horizonte_investimento', 'possui_offshore',
        'detalhes_offshore', 'possui_trust', 'detalhes_trust'
    ]
)
@handle_errors
@log_action(ActionType.UPDATE, "cliente")
def update_cliente(cliente_id: int):
    """Atualizar cliente existente"""
    current_user = auth_service.get_current_user()
    data = request.validated_data

    # Obter valores antigos para auditoria
    old_cliente = cliente_service.get_cliente_by_id(cliente_id, current_user.id)
    if not old_cliente:
        raise FileNotFoundError("Cliente não encontrado")

    # Atualizar cliente via service
    updated_cliente = cliente_service.update_cliente(
        cliente_id=cliente_id,
        user_id=current_user.id,
        data=data
    )

    # Invalidar caches
    cache_service.delete(f"cliente_{cliente_id}_{current_user.id}")
    cache_pattern = f"clientes_list_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log de auditoria
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="cliente",
        resource_id=str(cliente_id),
        old_values=old_cliente,
        new_values=updated_cliente,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'cliente_nome': updated_cliente['nome_completo']}
    )

    logging_service.info(
        "ClienteRoutes",
        "UPDATE_CLIENTE",
        f"Cliente {cliente_id} atualizado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'cliente_id': cliente_id, 'fields_updated': list(data.keys())}
    )

    return jsonify(updated_cliente)


@cliente_bp.route('/clientes/<int:cliente_id>', methods=['DELETE'])
@require_auth
@handle_errors
@log_action(ActionType.DELETE, "cliente")
def delete_cliente(cliente_id: int):
    """Excluir cliente (soft delete)"""
    current_user = auth_service.get_current_user()

    # Obter cliente para auditoria
    cliente = cliente_service.get_cliente_by_id(cliente_id, current_user.id)
    if not cliente:
        raise FileNotFoundError("Cliente não encontrado")

    # Excluir via service
    success = cliente_service.delete_cliente(
        cliente_id=cliente_id,
        user_id=current_user.id
    )

    if not success:
        raise Exception("Erro ao excluir cliente")

    # Invalidar caches
    cache_service.delete(f"cliente_{cliente_id}_{current_user.id}")
    cache_pattern = f"clientes_list_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log de auditoria
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="cliente",
        resource_id=str(cliente_id),
        old_values=cliente,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'cliente_nome': cliente['nome_completo']}
    )

    logging_service.info(
        "ClienteRoutes",
        "DELETE_CLIENTE",
        f"Cliente {cliente_id} excluído por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'cliente_id': cliente_id, 'cliente_nome': cliente['nome_completo']}
    )

    return jsonify({'message': 'Cliente excluído com sucesso'})


@cliente_bp.route('/clientes/<int:cliente_id>/restore', methods=['POST'])
@require_auth
@handle_errors
@log_action(ActionType.UPDATE, "cliente")
def restore_cliente(cliente_id: int):
    """Restaurar cliente excluído"""
    current_user = auth_service.get_current_user()

    # Restaurar via service
    cliente = cliente_service.restore_cliente(
        cliente_id=cliente_id,
        user_id=current_user.id
    )

    if not cliente:
        raise FileNotFoundError("Cliente não encontrado ou já está ativo")

    # Invalidar caches
    cache_service.delete(f"cliente_{cliente_id}_{current_user.id}")
    cache_pattern = f"clientes_list_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    # Log de auditoria
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="cliente",
        resource_id=str(cliente_id),
        new_values=cliente,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'cliente_nome': cliente['nome_completo'], 'action': 'restore'}
    )

    logging_service.info(
        "ClienteRoutes",
        "RESTORE_CLIENTE",
        f"Cliente {cliente_id} restaurado por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'cliente_id': cliente_id, 'cliente_nome': cliente['nome_completo']}
    )

    return jsonify(cliente)


@cliente_bp.route('/clientes/stats', methods=['GET'])
@require_auth
@handle_errors
@log_action(ActionType.READ, "cliente_stats")
def get_clientes_stats():
    """Obter estatísticas dos clientes"""
    current_user = auth_service.get_current_user()

    # Verificar cache
    cache_key = f"clientes_stats_{current_user.id}"
    cached_result = cache_service.get(cache_key)

    if cached_result:
        return jsonify(cached_result)

    # Obter estatísticas via service
    stats = cliente_service.get_clientes_statistics(current_user.id)

    # Cache por 15 minutos
    cache_service.set(cache_key, stats, ttl=900)

    logging_service.info(
        "ClienteRoutes",
        "GET_STATS",
        f"Estatísticas acessadas por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'total_clientes': stats.get('total_clientes', 0)}
    )

    return jsonify(stats)


@cliente_bp.route('/clientes/export', methods=['GET'])
@require_auth
@handle_errors
@log_action(ActionType.READ, "cliente_export")
def export_clientes():
    """Exportar clientes para CSV/Excel"""
    current_user = auth_service.get_current_user()
    format_type = request.args.get('format', 'csv').lower()

    if format_type not in ['csv', 'excel']:
        raise ValueError("Formato deve ser 'csv' ou 'excel'")

    # Exportar via service
    file_path = cliente_service.export_clientes(
        user_id=current_user.id,
        format_type=format_type
    )

    logging_service.info(
        "ClienteRoutes",
        "EXPORT_CLIENTES",
        f"Clientes exportados por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={'format': format_type, 'file_path': file_path}
    )

    return jsonify({
        'message': 'Exportação concluída',
        'download_url': f'/api/clientes/download/{file_path.split("/")[-1]}',
        'format': format_type
    })


@cliente_bp.route('/clientes/import', methods=['POST'])
@require_auth
@handle_errors
@log_action(ActionType.CREATE, "cliente_import")
def import_clientes():
    """Importar clientes de arquivo CSV/Excel"""
    current_user = auth_service.get_current_user()

    if 'file' not in request.files:
        raise ValueError("Arquivo não fornecido")

    file = request.files['file']
    if file.filename == '':
        raise ValueError("Nome do arquivo vazio")

    # Importar via service
    result = cliente_service.import_clientes(
        user_id=current_user.id,
        file=file
    )

    # Invalidar cache de listagem
    cache_pattern = f"clientes_list_{current_user.id}_*"
    cache_service.clear(cache_pattern)

    logging_service.info(
        "ClienteRoutes",
        "IMPORT_CLIENTES",
        f"Clientes importados por usuário {current_user.id}",
        user_id=current_user.id,
        metadata={
            'imported_count': result.get('imported_count', 0),
            'failed_count': result.get('failed_count', 0)
        }
    )

    return jsonify(result)


# Health check específico para clientes
@cliente_bp.route('/clientes/health', methods=['GET'])
def health_check():
    """Health check das funcionalidades de cliente"""
    try:
        # Verificar service
        health_status = cliente_service.health_check()

        return jsonify({
            'status': 'healthy',
            'service': 'cliente',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })

    except Exception as e:
        logging_service.error(
            "ClienteRoutes",
            "HEALTH_CHECK_ERROR",
            f"Erro no health check: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'cliente',
            'error': str(e)
        }), 500
