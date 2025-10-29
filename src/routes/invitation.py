"""
Routes for Invitation management

Handles all HTTP endpoints for invitation CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from src.services.auth_service import auth_service
from src.services.invitation_service import invitation_service
from src.services.logging_service import logging_service, ActionType, log_action


invitation_bp = Blueprint('invitation', __name__)


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
                    "InvitationRoutes",
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
                "InvitationRoutes",
                func.__name__.upper(),
                f"Validation error: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "InvitationRoutes",
                func.__name__.upper(),
                f"Permission denied: {str(e)}"
            )
            return jsonify({'error': 'Access denied'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "InvitationRoutes",
                func.__name__.upper(),
                f"Resource not found: {str(e)}"
            )
            return jsonify({'error': 'Resource not found'}), 404
        except Exception as e:
            logging_service.error(
                "InvitationRoutes",
                func.__name__.upper(),
                f"Internal error: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@invitation_bp.route('/invitations', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "invitation")
def list_invitations():
    """
    List invitations with pagination and filters
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - team_id: Filter by team ID
    - status: Filter by status (pending, accepted, declined, expired, cancelled)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    team_id = request.args.get('team_id', type=int)
    status = request.args.get('status', '').strip()
    
    # Fetch from service
    result = invitation_service.list_invitations(
        user_id=current_user.id,
        team_id=team_id,
        status=status if status else None,
        page=page,
        per_page=per_page
    )
    
    logging_service.info(
        "InvitationRoutes",
        "GET_INVITATIONS",
        f"Invitations listed for user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'page': page,
            'per_page': per_page,
            'team_id': team_id,
            'status': status,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@invitation_bp.route('/invitations/<int:invitation_id>', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "invitation")
def get_invitation(invitation_id):
    """Get a specific invitation by ID"""
    current_user = get_current_user()
    
    # Fetch from service
    invitation = invitation_service.get_invitation_by_id(
        invitation_id=invitation_id,
        user_id=current_user.id
    )
    
    if not invitation:
        raise FileNotFoundError("Invitation not found")
    
    logging_service.info(
        "InvitationRoutes",
        "GET_INVITATION",
        f"Invitation {invitation_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'invitation_id': invitation_id}
    )
    
    return jsonify(invitation)


@invitation_bp.route('/invitations/token/<token>', methods=['GET'])
@handle_errors
@log_action(ActionType.READ, "invitation")
def get_invitation_by_token(token):
    """Get invitation by token (public endpoint for invitation links)"""
    # Fetch from service
    invitation = invitation_service.get_invitation_by_token(token)
    
    if not invitation:
        raise FileNotFoundError("Invitation not found")
    
    logging_service.info(
        "InvitationRoutes",
        "GET_INVITATION_BY_TOKEN",
        f"Invitation accessed by token",
        metadata={'invitation_id': invitation.get('id')}
    )
    
    return jsonify(invitation)


@invitation_bp.route('/teams/<int:team_id>/invitations', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['invited_email'],
    optional_fields=['role', 'message', 'expires_in_days']
)
@handle_errors
@log_action(ActionType.CREATE, "invitation")
def create_invitation(team_id):
    """Create a new team invitation"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Create invitation via service
    result = invitation_service.create_invitation(
        team_id=team_id,
        inviter_id=current_user.id,
        invited_email=data['invited_email'],
        role=data.get('role', 'member'),
        message=data.get('message'),
        expires_in_days=data.get('expires_in_days', 7)
    )
    
    if not result.success:
        # Check if error is about user already being registered
        if "already registered" in result.error.lower():
            return jsonify({'error': result.error}), 409
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="invitation",
        resource_id=str(result.invitation['id']),
        new_values=result.invitation,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'team_id': team_id,
            'invited_email': data['invited_email'],
            'role': data.get('role', 'member')
        }
    )
    
    logging_service.info(
        "InvitationRoutes",
        "CREATE_INVITATION",
        f"Invitation created for team {team_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'invitation_id': result.invitation['id'],
            'team_id': team_id,
            'invited_email': data['invited_email']
        }
    )
    
    response_payload = {
        **(result.invitation or {}),
    }
    # Surface billing intent/preview if available
    if getattr(result, 'billing_intent', None) is not None:
        response_payload['billing_intent'] = result.billing_intent
    if getattr(result, 'overage_preview', None) is not None:
        response_payload['overage_preview'] = result.overage_preview

    return jsonify(response_payload), 201


@invitation_bp.route('/invitations/<token>/accept', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "invitation")
def accept_invitation(token):
    """Accept an invitation"""
    current_user = get_current_user()
    
    # Accept invitation via service
    result = invitation_service.accept_invitation(
        token=token,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="invitation",
        resource_id=str(result.invitation['id']),
        new_values={'status': 'accepted'},
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'invitation_id': result.invitation['id'],
            'team_id': result.invitation['team_id'],
            'action': 'accept'
        }
    )
    
    logging_service.info(
        "InvitationRoutes",
        "ACCEPT_INVITATION",
        f"Invitation accepted by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'invitation_id': result.invitation['id'],
            'team_id': result.invitation['team_id']
        }
    )
    
    return jsonify(result.invitation)


@invitation_bp.route('/invitations/<token>/decline', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "invitation")
def decline_invitation(token):
    """Decline an invitation"""
    current_user = get_current_user()
    
    # Decline invitation via service
    result = invitation_service.decline_invitation(
        token=token,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="invitation",
        resource_id=str(result.invitation['id']),
        new_values={'status': 'declined'},
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'invitation_id': result.invitation['id'],
            'team_id': result.invitation['team_id'],
            'action': 'decline'
        }
    )
    
    logging_service.info(
        "InvitationRoutes",
        "DECLINE_INVITATION",
        f"Invitation declined by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'invitation_id': result.invitation['id'],
            'team_id': result.invitation['team_id']
        }
    )
    
    return jsonify(result.invitation)


@invitation_bp.route('/invitations/<int:invitation_id>/cancel', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "invitation")
def cancel_invitation(invitation_id):
    """Cancel an invitation"""
    current_user = get_current_user()
    
    # Cancel invitation via service
    result = invitation_service.cancel_invitation(
        invitation_id=invitation_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="invitation",
        resource_id=str(invitation_id),
        new_values={'status': 'cancelled'},
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'invitation_id': invitation_id,
            'action': 'cancel'
        }
    )
    
    logging_service.info(
        "InvitationRoutes",
        "CANCEL_INVITATION",
        f"Invitation {invitation_id} cancelled by user {current_user.id}",
        user_id=current_user.id,
        metadata={'invitation_id': invitation_id}
    )
    
    return jsonify(result.invitation)


@invitation_bp.route('/invitations/<int:invitation_id>/resend', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.CREATE, "invitation")
def resend_invitation(invitation_id):
    """Resend an invitation"""
    current_user = get_current_user()
    
    # Resend invitation via service
    result = invitation_service.resend_invitation(
        invitation_id=invitation_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="invitation",
        resource_id=str(result.invitation['id']),
        new_values=result.invitation,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'original_invitation_id': invitation_id,
            'new_invitation_id': result.invitation['id'],
            'team_id': result.invitation['team_id'],
            'action': 'resend'
        }
    )
    
    logging_service.info(
        "InvitationRoutes",
        "RESEND_INVITATION",
        f"Invitation {invitation_id} resent by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'original_invitation_id': invitation_id,
            'new_invitation_id': result.invitation['id']
        }
    )
    
    return jsonify(result.invitation), 201


@invitation_bp.route('/invitations/stats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "invitation_stats")
def get_invitation_stats():
    """Get invitation statistics for current user"""
    current_user = get_current_user()
    
    # Get stats from service
    stats = invitation_service.get_invitation_statistics(current_user.id)
    
    logging_service.info(
        "InvitationRoutes",
        "GET_STATS",
        f"Statistics accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'total_invitations': stats.get('total_invitations', 0)}
    )
    
    return jsonify(stats)


@invitation_bp.route('/invitations/cleanup', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "invitation_cleanup")
def cleanup_expired_invitations():
    """Cleanup expired invitations (admin only)"""
    current_user = get_current_user()
    
    # Check if user is admin (you might want to add proper admin check)
    # For now, allowing any authenticated user to cleanup
    
    # Cleanup expired invitations
    expired_count = invitation_service.cleanup_expired_invitations()
    
    logging_service.info(
        "InvitationRoutes",
        "CLEANUP_EXPIRED",
        f"Expired invitations cleaned up by user {current_user.id}",
        user_id=current_user.id,
        metadata={'expired_count': expired_count}
    )
    
    return jsonify({
        'message': f'Cleaned up {expired_count} expired invitations',
        'expired_count': expired_count
    })


# Health check
@invitation_bp.route('/invitations/health', methods=['GET'])
def health_check():
    """Health check for invitation endpoints"""
    try:
        health_status = invitation_service.health_check()
        
        return jsonify({
            'status': 'healthy',
            'service': 'invitation',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })
        
    except Exception as e:
        logging_service.error(
            "InvitationRoutes",
            "HEALTH_CHECK_ERROR",
            f"Health check error: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'invitation',
            'error': str(e)
        }), 500


