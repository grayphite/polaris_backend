"""
Routes for Chat management

Handles all HTTP endpoints for chat CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from src.services.auth_service import auth_service
from src.services.chat_service import chat_service
from src.services.logging_service import logging_service, ActionType, log_action


chat_bp = Blueprint('chat', __name__)


def validate_request_data(required_fields=None, optional_fields=None):
    """
    Decorator for request data validation
    
    Args:
        required_fields: List of required fields
        optional_fields: List of optional allowed fields
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                data = request.get_json() if request.method in ['POST', 'PUT'] else {}
                
                # Validate required fields
                if required_fields:
                    for field in required_fields:
                        if field not in data or not data[field]:
                            return jsonify({
                                'error': f'Field {field} is required',
                                'field': field
                            }), 400
                
                # Filter allowed fields
                if optional_fields:
                    allowed_fields = (required_fields or []) + optional_fields
                    filtered_data = {k: v for k, v in data.items() 
                                   if k in allowed_fields}
                    request.validated_data = filtered_data
                else:
                    request.validated_data = data
                
                return func(*args, **kwargs)
                
            except Exception as e:
                logging_service.error(
                    "ChatRoutes",
                    "VALIDATION_ERROR",
                    f"Validation error: {str(e)}",
                    error_details={'error': str(e)}
                )
                return jsonify({'error': 'Data validation failed'}), 400
        
        return wrapper
    return decorator


def handle_errors(func):
    """Decorator for centralized error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            logging_service.warning(
                "ChatRoutes",
                func.__name__.upper(),
                f"Validation error: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "ChatRoutes",
                func.__name__.upper(),
                f"Permission denied: {str(e)}"
            )
            return jsonify({'error': 'Access denied'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "ChatRoutes",
                func.__name__.upper(),
                f"Resource not found: {str(e)}"
            )
            return jsonify({'error': 'Resource not found'}), 404
        except Exception as e:
            logging_service.error(
                "ChatRoutes",
                func.__name__.upper(),
                f"Internal error: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@chat_bp.route('/chats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "chat")
def list_chats():
    """
    List chats with pagination and search
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    - project_id: Filter by project ID
    - include_deleted: Include soft-deleted chats (default: false)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    project_id = request.args.get('project_id', type=int)
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    
    # Fetch from service
    result = chat_service.list_chats(
        user_id=current_user.id,
        project_id=project_id,
        page=page,
        per_page=per_page,
        search=search,
        include_deleted=include_deleted
    )
    
    logging_service.info(
        "ChatRoutes",
        "GET_CHATS",
        f"Chats listed for user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'page': page,
            'per_page': per_page,
            'search': search,
            'project_id': project_id,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@chat_bp.route('/chats/<int:chat_id>', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "chat")
def get_chat(chat_id):
    """Get a specific chat by ID"""
    current_user = get_current_user()
    
    # Fetch from service
    chat = chat_service.get_chat_by_id(
        chat_id=chat_id,
        user_id=current_user.id
    )
    
    if not chat:
        raise FileNotFoundError("Chat not found")
    
    logging_service.info(
        "ChatRoutes",
        "GET_CHAT",
        f"Chat {chat_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'chat_id': chat_id}
    )
    
    return jsonify(chat)


@chat_bp.route('/projects/<int:project_id>/chats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "chat")
def list_chats_by_project(project_id):
    """
    List all chats for a specific project
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    
    # Fetch from service
    result = chat_service.list_chats_by_project(
        project_id=project_id,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        search=search
    )
    
    logging_service.info(
        "ChatRoutes",
        "GET_PROJECT_CHATS",
        f"Chats for project {project_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'project_id': project_id,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@chat_bp.route('/chats', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['name', 'project_id'],
    optional_fields=['description']
)
@handle_errors
@log_action(ActionType.CREATE, "chat")
def create_chat():
    """Create a new chat"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Create chat via service
    result = chat_service.create_chat(
        name=data['name'],
        project_id=data['project_id'],
        user_id=current_user.id,
        description=data.get('description')
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="chat",
        resource_id=str(result.chat['id']),
        new_values=result.chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'name': result.chat['name'],
            'project_id': result.chat['project_id']
        }
    )
    
    logging_service.info(
        "ChatRoutes",
        "CREATE_CHAT",
        f"Chat created: {result.chat['name']} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'chat_id': result.chat['id'],
            'project_id': result.chat['project_id']
        }
    )
    
    return jsonify(result.chat), 201


@chat_bp.route('/chats/<int:chat_id>', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(
    optional_fields=['name', 'description']
)
@handle_errors
@log_action(ActionType.UPDATE, "chat")
def update_chat(chat_id):
    """Update an existing chat"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Get old values for audit
    old_chat = chat_service.get_chat_by_id(chat_id, current_user.id)
    if not old_chat:
        raise FileNotFoundError("Chat not found")
    
    # Update via service
    result = chat_service.update_chat(
        chat_id=chat_id,
        user_id=current_user.id,
        data=data
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="chat",
        resource_id=str(chat_id),
        old_values=old_chat,
        new_values=result.chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'fields_updated': list(data.keys())}
    )
    
    logging_service.info(
        "ChatRoutes",
        "UPDATE_CHAT",
        f"Chat {chat_id} updated by user {current_user.id}",
        user_id=current_user.id,
        metadata={'chat_id': chat_id}
    )
    
    return jsonify(result.chat)


@chat_bp.route('/chats/<int:chat_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "chat")
def delete_chat(chat_id):
    """Soft delete a chat"""
    current_user = get_current_user()
    
    # Get chat for audit
    chat = chat_service.get_chat_by_id(chat_id, current_user.id)
    if not chat:
        raise FileNotFoundError("Chat not found")
    
    # Delete via service
    result = chat_service.permanent_delete_chat(
        chat_id=chat_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="chat",
        resource_id=str(chat_id),
        old_values=chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'name': chat['name']}
    )
    
    logging_service.info(
        "ChatRoutes",
        "DELETE_CHAT",
        f"Chat {chat_id} deleted by user {current_user.id}",
        user_id=current_user.id,
        metadata={'chat_id': chat_id}
    )
    
    return jsonify({'message': 'Chat deleted successfully'})


@chat_bp.route('/chats/<int:chat_id>/restore', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "chat")
def restore_chat(chat_id):
    """Restore a soft-deleted chat"""
    current_user = get_current_user()
    
    # Restore via service
    result = chat_service.restore_chat(
        chat_id=chat_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="chat",
        resource_id=str(chat_id),
        new_values=result.chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'action': 'restore', 'name': result.chat['name']}
    )
    
    logging_service.info(
        "ChatRoutes",
        "RESTORE_CHAT",
        f"Chat {chat_id} restored by user {current_user.id}",
        user_id=current_user.id,
        metadata={'chat_id': chat_id}
    )
    
    return jsonify(result.chat)


@chat_bp.route('/chats/stats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "chat_stats")
def get_chat_stats():
    """Get chat statistics for current user"""
    current_user = get_current_user()
    
    # Optional project filter
    project_id = request.args.get('project_id', type=int)
    
    # Get stats from service
    stats = chat_service.get_chat_statistics(current_user.id, project_id)
    
    logging_service.info(
        "ChatRoutes",
        "GET_STATS",
        f"Statistics accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'total_chats': stats.get('total_chats', 0),
            'project_id': project_id
        }
    )
    
    return jsonify(stats)


# Health check
@chat_bp.route('/chats/health', methods=['GET'])
def health_check():
    """Health check for chat endpoints"""
    try:
        health_status = chat_service.health_check()
        
        return jsonify({
            'status': 'healthy',
            'service': 'chat',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })
        
    except Exception as e:
        logging_service.error(
            "ChatRoutes",
            "HEALTH_CHECK_ERROR",
            f"Health check error: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'chat',
            'error': str(e)
        }), 500


