"""
Anthropic Chat Routes - HTTP endpoints for Anthropic Claude chat management

Handles all HTTP endpoints for AI chat CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g, Response, stream_with_context
import json
import time
import os

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
        new_values=result.ai_chat,  # This is already a serialized dict from service
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
    optional_fields=['conversation_context', 'context_limit', 'file_references', 'file_reference_details', 'use_rag', 'referenced_chat_id']
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
    
    # Validate referenced_chat_id if provided
    referenced_chat_id = data.get('referenced_chat_id')
    if referenced_chat_id is not None:
        try:
            referenced_chat_id = int(referenced_chat_id)
            # Additional validation will be done in service layer
        except (ValueError, TypeError):
            return jsonify({'error': 'referenced_chat_id must be a valid integer'}), 400
    
    # Create AI chat via service (this will also send to Anthropic)
    result = anthropic_chat_service.create_ai_chat(
        chat_id=data['chat_id'],
        user_id=current_user.id,
        user_question=data['user_question'],
        conversation_context=data.get('conversation_context'),
        context_limit=context_limit,
        file_references=data.get('file_references'),
        file_reference_details=data.get('file_reference_details'),
        use_rag=data.get('use_rag', False),
        referenced_chat_id=referenced_chat_id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="ai_chat",
        resource_id=str(result.ai_chat['id']),
        new_values=result.ai_chat,  # This is already a serialized dict from service
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


@anthropic_chat_bp.route('/ai-chats/send-message-stream', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['chat_id', 'user_question'],
    optional_fields=['conversation_context', 'context_limit', 'file_references', 'file_reference_details', 'use_rag', 'referenced_chat_id']
)
@handle_errors
@log_action(ActionType.CREATE, "ai_chat_stream")
def send_message_stream():
    """
    Send a message to Anthropic Claude with streaming response
    
    This endpoint provides real-time streaming of AI responses using Server-Sent Events (SSE).
    The response is streamed to the client as it's generated, providing a better user experience.
    
    Returns:
        Server-Sent Events stream with real-time AI response data
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
    
    # Validate referenced_chat_id if provided
    referenced_chat_id = data.get('referenced_chat_id')
    if referenced_chat_id is not None:
        try:
            referenced_chat_id = int(referenced_chat_id)
            # Additional validation will be done in service layer
        except (ValueError, TypeError):
            return jsonify({'error': 'referenced_chat_id must be a valid integer'}), 400
    
    # Production-grade rate limiting (aligned with Anthropic's capabilities)
    rate_limit_key = f"ai_chat_stream_rate_limit_{current_user.id}"
    current_requests = getattr(g, 'cache_service', None)

    if current_requests:
        # Use service configuration for rate limiting
        streaming_rate_limit = anthropic_chat_service.streaming_rate_limit
        current_count = current_requests.get(rate_limit_key) or 0

        if current_count >= streaming_rate_limit:
            return jsonify({
                'error': 'Streaming rate limit exceeded',
                'retry_after': 3600,
                'limit': streaming_rate_limit,
                'message': f'Maximum {streaming_rate_limit} streaming requests per hour allowed'
            }), 429
        
        # Increment counter
        current_requests.set(rate_limit_key, current_count + 1, ttl=3600)
    
    def generate_stream():
        """
        Generator function for streaming response
        Handles the complete streaming workflow with proper error handling
        """
        start_time = time.time()
        stream_id = f"stream_{int(start_time * 1000)}_{current_user.id}"
        
        try:
            # Log streaming start
            logging_service.info(
                "AnthropicChatRoutes",
                "SEND_MESSAGE_STREAM_START",
                f"Streaming started for chat {data['chat_id']} by user {current_user.id}",
                user_id=current_user.id,
                metadata={
                    'stream_id': stream_id,
                    'chat_id': data['chat_id'],
                    'user_question_length': len(data['user_question']),
                    'file_references_count': len(data.get('file_references', [])),
                    'context_limit': context_limit
                }
            )
            
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connection_established', 'stream_id': stream_id})}\n\n"
            
            # Stream AI chat creation
            for event in anthropic_chat_service.create_ai_chat_stream(
                chat_id=data['chat_id'],
                user_id=current_user.id,
                user_question=data['user_question'],
                conversation_context=data.get('conversation_context'),
                context_limit=context_limit,
                file_references=data.get('file_references'),
                file_reference_details=data.get('file_reference_details'),
                use_rag=data.get('use_rag', False),
                referenced_chat_id=referenced_chat_id
            ):
                # Add stream metadata to each event
                event['stream_id'] = stream_id
                event['timestamp'] = time.time()
                
                # Handle different event types
                if event.get('type') == 'error':
                    # Log error
                    logging_service.error(
                        "AnthropicChatRoutes",
                        "SEND_MESSAGE_STREAM_ERROR",
                        f"Streaming error for chat {data['chat_id']}: {event.get('error', {}).get('message', 'Unknown error')}",
                        user_id=current_user.id,
                        metadata={
                            'stream_id': stream_id,
                            'chat_id': data['chat_id'],
                            'error_type': event.get('error', {}).get('type', 'unknown'),
                            'error_message': event.get('error', {}).get('message', 'Unknown error')
                        }
                    )
                    
                    # Send error event
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                
                elif event.get('type') == 'stream_start':
                    # Log stream start
                    logging_service.info(
                        "AnthropicChatRoutes",
                        "SEND_MESSAGE_STREAM_PROCESSING",
                        f"Stream processing started for chat {data['chat_id']}",
                        user_id=current_user.id,
                        metadata={
                            'stream_id': stream_id,
                            'chat_id': data['chat_id'],
                            'model': event.get('metadata', {}).get('model', 'unknown')
                        }
                    )
                    
                    # Send stream start event
                    yield f"data: {json.dumps(event)}\n\n"
                
                elif event.get('type') == 'content_block_delta':
                    # Stream content deltas in real-time
                    yield f"data: {json.dumps(event)}\n\n"
                
                elif event.get('type') == 'stream_complete':
                    # Log successful completion
                    processing_time = time.time() - start_time
                    ai_chat_id = event.get('ai_chat', {}).get('id')
                    
                    logging_service.info(
                        "AnthropicChatRoutes",
                        "SEND_MESSAGE_STREAM_COMPLETE",
                        f"Streaming completed for chat {data['chat_id']} in {processing_time:.2f}s",
                        user_id=current_user.id,
                        metadata={
                            'stream_id': stream_id,
                            'chat_id': data['chat_id'],
                            'ai_chat_id': ai_chat_id,
                            'processing_time': processing_time,
                            'success': True
                        }
                    )
                    
                    # Add processing time to final event
                    event['processing_time'] = processing_time
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                
                else:
                    # Pass through other events
                    yield f"data: {json.dumps(event)}\n\n"
            
            # Send final stream end marker
            yield f"data: {json.dumps({'type': 'stream_end', 'stream_id': stream_id})}\n\n"
            
        except Exception as e:
            # Log unexpected error
            processing_time = time.time() - start_time
            error_msg = f"Unexpected error in streaming: {str(e)}"
            
            logging_service.error(
                "AnthropicChatRoutes",
                "SEND_MESSAGE_STREAM_UNEXPECTED_ERROR",
                error_msg,
                user_id=current_user.id,
                metadata={
                    'stream_id': stream_id,
                    'chat_id': data['chat_id'],
                    'processing_time': processing_time,
                    'error': str(e)
                }
            )
            
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'error': {'type': 'unexpected_error', 'message': error_msg}, 'stream_id': stream_id})}\n\n"
        
        finally:
            # Log stream completion (success or failure)
            total_time = time.time() - start_time
            logging_service.info(
                "AnthropicChatRoutes",
                "SEND_MESSAGE_STREAM_FINAL",
                f"Stream session ended for chat {data['chat_id']} (total time: {total_time:.2f}s)",
                user_id=current_user.id,
                metadata={
                    'stream_id': stream_id,
                    'chat_id': data['chat_id'],
                    'total_time': total_time
                }
            )
    
    # Production-grade streaming headers (optimized for millions of users)
    headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',  # Disable nginx buffering
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control, Authorization, Content-Type, X-Requested-With',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Max-Age': '86400',  # 24 hours
        'Keep-Alive': 'timeout=300, max=1000'  # 5 minutes timeout, 1000 requests
    }
    
    # Note: Compression disabled for streaming to avoid ERR_CONTENT_DECODING_FAILED
    # Server-Sent Events work better without compression for real-time streaming
    # Compression can be enabled for non-streaming endpoints
    
    return Response(
        stream_with_context(generate_stream()),
        mimetype='text/event-stream',
        headers=headers
    )


@anthropic_chat_bp.route('/ai-chats/refresh-chat-summary', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['referenced_chat_id'],
    optional_fields=[]
)
@handle_errors
@log_action(ActionType.UPDATE, "chat_reference")
def refresh_chat_summary():
    """
    Refresh the summary for a referenced chat
    
    This endpoint allows users to manually refresh the AI-generated summary
    of a referenced chat, useful when new messages have been added to the referenced chat.
    
    Returns:
        Updated chat reference summary data
    """
    current_user = get_current_user()
    data = request.validated_data
    referenced_chat_id = data['referenced_chat_id']
    
    # Validate referenced_chat_id
    try:
        referenced_chat_id = int(referenced_chat_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'referenced_chat_id must be a valid integer'}), 400
    
    # Verify user has access to referenced chat
    if not anthropic_chat_service._verify_chat_access(referenced_chat_id, current_user.id):
        return jsonify({'error': 'Chat not found or access denied'}), 404
    
    # Refresh the summary
    chat_reference = anthropic_chat_service.refresh_chat_summary(referenced_chat_id, current_user.id)
    
    if not chat_reference:
        return jsonify({'error': 'Failed to refresh chat summary'}), 500
    
    # Log the refresh
    logging_service.info(
        "AnthropicChatRoutes",
        "REFRESH_CHAT_SUMMARY",
        f"Chat summary refreshed for chat {referenced_chat_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'referenced_chat_id': referenced_chat_id,
            'summary_tokens': chat_reference.summary_tokens,
            'message_count': chat_reference.referenced_chat_message_count
        }
    )
    
    return jsonify({
        'success': True,
        'chat_reference': chat_reference.to_dict(),
        'message': 'Chat summary refreshed successfully'
    }), 200


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
