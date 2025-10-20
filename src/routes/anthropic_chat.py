"""
Anthropic Chat Routes - HTTP endpoints for Anthropic Claude chat management

Handles all HTTP endpoints for AI chat CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from src.services.auth_service import auth_service
from src.services.anthropic_chat_service import anthropic_chat_service
from src.services.logging_service import logging_service, ActionType, log_action


anthropic_chat_bp = Blueprint('anthropic_chat', __name__)


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
                    "AnthropicChatRoutes",
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
                "AnthropicChatRoutes",
                func.__name__.upper(),
                f"Validation error: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "AnthropicChatRoutes",
                func.__name__.upper(),
                f"Permission denied: {str(e)}"
            )
            return jsonify({'error': 'Access denied'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "AnthropicChatRoutes",
                func.__name__.upper(),
                f"Resource not found: {str(e)}"
            )
            return jsonify({'error': 'Resource not found'}), 404
        except Exception as e:
            logging_service.error(
                "AnthropicChatRoutes",
                func.__name__.upper(),
                f"Internal error: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@anthropic_chat_bp.route('/chats/<int:chat_id>/ai-chats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "ai_chat")
def list_ai_chats(chat_id):
    """
    List AI chats for a specific chat with pagination and search
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    - include_deleted: Include soft-deleted AI chats (default: false)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    
    # Fetch from service
    result = anthropic_chat_service.list_ai_chats(
        chat_id=chat_id,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        search=search,
        include_deleted=include_deleted
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "GET_AI_CHATS",
        f"AI chats listed for chat {chat_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'chat_id': chat_id,
            'page': page,
            'per_page': per_page,
            'search': search,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@anthropic_chat_bp.route('/ai-chats/<int:ai_chat_id>', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "ai_chat")
def get_ai_chat(ai_chat_id):
    """Get a specific AI chat by ID"""
    current_user = get_current_user()
    
    # Fetch from service
    ai_chat = anthropic_chat_service.get_ai_chat_by_id(
        ai_chat_id=ai_chat_id,
        user_id=current_user.id
    )
    
    if not ai_chat:
        raise FileNotFoundError("AI chat not found")
    
    logging_service.info(
        "AnthropicChatRoutes",
        "GET_AI_CHAT",
        f"AI chat {ai_chat_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'ai_chat_id': ai_chat_id}
    )
    
    return jsonify(ai_chat)


@anthropic_chat_bp.route('/chats/<int:chat_id>/ai-chats', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['user_question'],
    optional_fields=['conversation_context', 'file_references', 'file_reference_details']
)
@handle_errors
@log_action(ActionType.CREATE, "ai_chat")
def create_ai_chat(chat_id):
    """Create a new AI chat conversation"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Create AI chat via service
    result = anthropic_chat_service.create_ai_chat(
        chat_id=chat_id,
        user_id=current_user.id,
        user_question=data['user_question'],
        conversation_context=data.get('conversation_context'),
        file_references=data.get('file_references'),
        file_reference_details=data.get('file_reference_details')
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="ai_chat",
        resource_id=str(result.ai_chat['id']),
        new_values=result.ai_chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'chat_id': chat_id,
            'ai_provider': result.ai_chat['ai_model_provider']
        }
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "CREATE_AI_CHAT",
        f"AI chat created for chat {chat_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'ai_chat_id': result.ai_chat['id'],
            'chat_id': chat_id,
            'ai_model': result.ai_chat['ai_model']
        }
    )
    
    return jsonify(result.ai_chat), 201


@anthropic_chat_bp.route('/ai-chats/<int:ai_chat_id>', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(
    optional_fields=['user_question', 'ai_answer', 'conversation_context', 'context_metadata']
)
@handle_errors
@log_action(ActionType.UPDATE, "ai_chat")
def update_ai_chat(ai_chat_id):
    """Update an existing AI chat"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Get old values for audit
    old_ai_chat = anthropic_chat_service.get_ai_chat_by_id(ai_chat_id, current_user.id)
    if not old_ai_chat:
        raise FileNotFoundError("AI chat not found")
    
    # Update via service
    result = anthropic_chat_service.update_ai_chat(
        ai_chat_id=ai_chat_id,
        user_id=current_user.id,
        data=data
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="ai_chat",
        resource_id=str(ai_chat_id),
        old_values=old_ai_chat,
        new_values=result.ai_chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'fields_updated': list(data.keys())}
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "UPDATE_AI_CHAT",
        f"AI chat {ai_chat_id} updated by user {current_user.id}",
        user_id=current_user.id,
        metadata={'ai_chat_id': ai_chat_id}
    )
    
    return jsonify(result.ai_chat)


@anthropic_chat_bp.route('/ai-chats/<int:ai_chat_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "ai_chat")
def delete_ai_chat(ai_chat_id):
    """Soft delete an AI chat"""
    current_user = get_current_user()
    
    # Get AI chat for audit
    ai_chat = anthropic_chat_service.get_ai_chat_by_id(ai_chat_id, current_user.id)
    if not ai_chat:
        raise FileNotFoundError("AI chat not found")
    
    # Delete via service
    result = anthropic_chat_service.delete_ai_chat(
        ai_chat_id=ai_chat_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="ai_chat",
        resource_id=str(ai_chat_id),
        old_values=ai_chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'chat_id': ai_chat['chat_id']}
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "DELETE_AI_CHAT",
        f"AI chat {ai_chat_id} deleted by user {current_user.id}",
        user_id=current_user.id,
        metadata={'ai_chat_id': ai_chat_id}
    )
    
    return jsonify({'message': 'AI chat deleted successfully'})


@anthropic_chat_bp.route('/ai-chats/<int:ai_chat_id>/restore', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "ai_chat")
def restore_ai_chat(ai_chat_id):
    """Restore a soft-deleted AI chat"""
    current_user = get_current_user()
    
    # Restore via service
    result = anthropic_chat_service.restore_ai_chat(
        ai_chat_id=ai_chat_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="ai_chat",
        resource_id=str(ai_chat_id),
        new_values=result.ai_chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'action': 'restore', 'chat_id': result.ai_chat['chat_id']}
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "RESTORE_AI_CHAT",
        f"AI chat {ai_chat_id} restored by user {current_user.id}",
        user_id=current_user.id,
        metadata={'ai_chat_id': ai_chat_id}
    )
    
    return jsonify(result.ai_chat)


@anthropic_chat_bp.route('/ai-chats/stats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "ai_chat_stats")
def get_ai_chat_stats():
    """Get AI chat statistics for current user"""
    current_user = get_current_user()
    
    # Optional chat filter
    chat_id = request.args.get('chat_id', type=int)
    
    # Get stats from service
    stats = anthropic_chat_service.get_ai_chat_statistics(current_user.id, chat_id)
    
    logging_service.info(
        "AnthropicChatRoutes",
        "GET_STATS",
        f"AI chat statistics accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'total_ai_chats': stats.get('total_ai_chats', 0),
            'chat_id': chat_id
        }
    )
    
    return jsonify(stats)


@anthropic_chat_bp.route('/ai-chats/send-message', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['chat_id', 'user_question'],
    optional_fields=['conversation_context', 'context_limit', 'file_references', 'file_reference_details']
)
@handle_errors
@log_action(ActionType.CREATE, "ai_chat")
def send_message():
    """
    Send a message to Anthropic Claude and create AI chat record
    
    This is a unified endpoint that handles both simple chat and file-attached chat.
    If file_references is provided in the payload, files will be included in the conversation.
    Otherwise, it will be treated as a simple text-only chat.
    """
    current_user = get_current_user()
    data = request.validated_data
    
    # Validate context_limit if provided
    context_limit = data.get('context_limit', 10)
    if context_limit is not None:
        try:
            context_limit = int(context_limit)
            if context_limit < 1 or context_limit > 50:
                return jsonify({'error': 'context_limit must be between 1 and 50'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'context_limit must be a valid integer'}), 400
    
    # Create AI chat via service (this will also send to Anthropic)
    result = anthropic_chat_service.create_ai_chat(
        chat_id=data['chat_id'],
        user_id=current_user.id,
        user_question=data['user_question'],
        conversation_context=data.get('conversation_context'),
        context_limit=context_limit,
        file_references=data.get('file_references'),
        file_reference_details=data.get('file_reference_details')
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="ai_chat",
        resource_id=str(result.ai_chat['id']),
        new_values=result.ai_chat,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'chat_id': data['chat_id'],
            'action': 'send_message'
        }
    )
    
    logging_service.info(
        "AnthropicChatRoutes",
        "SEND_MESSAGE",
        f"Message sent via AI chat for chat {data['chat_id']} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'ai_chat_id': result.ai_chat['id'],
            'chat_id': data['chat_id'],
            'ai_model': result.ai_chat['ai_model']
        }
    )
    
    return jsonify({
        'success': True,
        'ai_chat': result.ai_chat,
        'message': 'Message sent successfully'
    }), 201


# Health check
@anthropic_chat_bp.route('/ai-chats/health', methods=['GET'])
def health_check():
    """Health check for Anthropic chat endpoints"""
    try:
        health_status = anthropic_chat_service.health_check()
        
        return jsonify({
            'status': 'healthy',
            'service': 'anthropic_chat',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })
        
    except Exception as e:
        logging_service.error(
            "AnthropicChatRoutes",
            "HEALTH_CHECK_ERROR",
            f"Health check error: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'anthropic_chat',
            'error': str(e)
        }), 500
