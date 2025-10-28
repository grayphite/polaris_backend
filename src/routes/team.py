"""
Routes for Team management

Handles all HTTP endpoints for team CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from src.services.auth_service import auth_service
from src.services.team_service import team_service
from src.services.logging_service import logging_service, ActionType, log_action


team_bp = Blueprint('team', __name__)


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
                    "TeamRoutes",
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
                "TeamRoutes",
                func.__name__.upper(),
                f"Validation error: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "TeamRoutes",
                func.__name__.upper(),
                f"Permission denied: {str(e)}"
            )
            return jsonify({'error': 'Access denied'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "TeamRoutes",
                func.__name__.upper(),
                f"Resource not found: {str(e)}"
            )
            return jsonify({'error': 'Resource not found'}), 404
        except Exception as e:
            logging_service.error(
                "TeamRoutes",
                func.__name__.upper(),
                f"Internal error: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@team_bp.route('/teams', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "team")
def list_teams():
    """
    List teams with pagination and search
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    - include_deleted: Include soft-deleted teams (default: false)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    
    # Fetch from service
    result = team_service.list_teams(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        search=search,
        include_deleted=include_deleted
    )
    
    logging_service.info(
        "TeamRoutes",
        "GET_TEAMS",
        f"Teams listed for user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'page': page,
            'per_page': per_page,
            'search': search,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@team_bp.route('/teams/<int:team_id>', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "team")
def get_team(team_id):
    """Get a specific team by ID"""
    current_user = get_current_user()
    
    # Fetch from service
    team = team_service.get_team_by_id(
        team_id=team_id,
        user_id=current_user.id
    )
    
    if not team:
        raise FileNotFoundError("Team not found")
    
    logging_service.info(
        "TeamRoutes",
        "GET_TEAM",
        f"Team {team_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'team_id': team_id}
    )
    
    return jsonify(team)


@team_bp.route('/teams', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['name'],
    optional_fields=['description']
)
@handle_errors
@log_action(ActionType.CREATE, "team")
def create_team():
    """Create a new team"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Create team via service
    result = team_service.create_team(
        name=data['name'],
        user_id=current_user.id,
        description=data.get('description')
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="team",
        resource_id=str(result.team['id']),
        new_values=result.team,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'name': result.team['name']}
    )
    
    logging_service.info(
        "TeamRoutes",
        "CREATE_TEAM",
        f"Team created: {result.team['name']} by user {current_user.id}",
        user_id=current_user.id,
        metadata={'team_id': result.team['id']}
    )
    
    return jsonify(result.team), 201


@team_bp.route('/teams/<int:team_id>', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(
    optional_fields=['name', 'description']
)
@handle_errors
@log_action(ActionType.UPDATE, "team")
def update_team(team_id):
    """Update an existing team"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Get old values for audit
    old_team = team_service.get_team_by_id(team_id, current_user.id)
    if not old_team:
        raise FileNotFoundError("Team not found")
    
    # Update via service
    result = team_service.update_team(
        team_id=team_id,
        user_id=current_user.id,
        data=data
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="team",
        resource_id=str(team_id),
        old_values=old_team,
        new_values=result.team,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'fields_updated': list(data.keys())}
    )
    
    logging_service.info(
        "TeamRoutes",
        "UPDATE_TEAM",
        f"Team {team_id} updated by user {current_user.id}",
        user_id=current_user.id,
        metadata={'team_id': team_id}
    )
    
    return jsonify(result.team)


@team_bp.route('/teams/<int:team_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "team")
def delete_team(team_id):
    """Soft delete a team"""
    current_user = get_current_user()
    
    # Get team for audit
    team = team_service.get_team_by_id(team_id, current_user.id)
    if not team:
        raise FileNotFoundError("Team not found")
    
    # Delete via service
    result = team_service.delete_team(
        team_id=team_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="team",
        resource_id=str(team_id),
        old_values=team,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'name': team['name']}
    )
    
    logging_service.info(
        "TeamRoutes",
        "DELETE_TEAM",
        f"Team {team_id} deleted by user {current_user.id}",
        user_id=current_user.id,
        metadata={'team_id': team_id}
    )
    
    return jsonify({'message': 'Team deleted successfully'})


@team_bp.route('/teams/<int:team_id>/members', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "team_members")
def list_team_members(team_id):
    """
    List all members of a team
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    
    # Fetch from service
    result = team_service.list_team_members(
        team_id=team_id,
        user_id=current_user.id,
        page=page,
        per_page=per_page
    )
    
    logging_service.info(
        "TeamRoutes",
        "GET_TEAM_MEMBERS",
        f"Team members for team {team_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'team_id': team_id,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@team_bp.route('/teams/<int:team_id>/members', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['user_id'],
    optional_fields=['role']
)
@handle_errors
@log_action(ActionType.CREATE, "team_member")
def add_team_member(team_id):
    """Add a member to a team"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Add member via service
    result = team_service.add_team_member(
        team_id=team_id,
        user_id=current_user.id,
        member_user_id=data['user_id'],
        role=data.get('role', 'member')
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="team_member",
        resource_id=str(result.member['id']),
        new_values=result.member,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'team_id': team_id,
            'member_user_id': data['user_id'],
            'role': data.get('role', 'member')
        }
    )
    
    logging_service.info(
        "TeamRoutes",
        "ADD_TEAM_MEMBER",
        f"Member added to team {team_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'team_id': team_id,
            'member_user_id': data['user_id']
        }
    )
    
    return jsonify(result.member), 201


@team_bp.route('/teams/<int:team_id>/members/<int:member_user_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "team_member")
def remove_team_member(team_id, member_user_id):
    """Remove a member from a team"""
    current_user = get_current_user()
    
    # Remove member via service
    result = team_service.remove_team_member(
        team_id=team_id,
        user_id=current_user.id,
        member_user_id=member_user_id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="team_member",
        resource_id=f"{team_id}_{member_user_id}",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'team_id': team_id,
            'member_user_id': member_user_id
        }
    )
    
    logging_service.info(
        "TeamRoutes",
        "REMOVE_TEAM_MEMBER",
        f"Member removed from team {team_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'team_id': team_id,
            'member_user_id': member_user_id
        }
    )
    
    return jsonify({'message': 'Member removed successfully'})


@team_bp.route('/teams/<int:team_id>/members/<int:member_user_id>/role', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['role']
)
@handle_errors
@log_action(ActionType.UPDATE, "team_member_role")
def update_team_member_role(team_id, member_user_id):
    """Update a team member's role"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Update role via service
    result = team_service.update_team_member_role(
        team_id=team_id,
        user_id=current_user.id,
        member_user_id=member_user_id,
        new_role=data['role']
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="team_member_role",
        resource_id=f"{team_id}_{member_user_id}",
        new_values={'role': data['role']},
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={
            'team_id': team_id,
            'member_user_id': member_user_id,
            'new_role': data['role']
        }
    )
    
    logging_service.info(
        "TeamRoutes",
        "UPDATE_TEAM_MEMBER_ROLE",
        f"Member role updated in team {team_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'team_id': team_id,
            'member_user_id': member_user_id,
            'new_role': data['role']
        }
    )
    
    return jsonify(result.member)


@team_bp.route('/teams/stats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "team_stats")
def get_team_stats():
    """Get team statistics for current user"""
    current_user = get_current_user()
    
    # Get stats from service
    stats = team_service.get_team_statistics(current_user.id)
    
    logging_service.info(
        "TeamRoutes",
        "GET_STATS",
        f"Statistics accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'total_teams': stats.get('total_teams', 0)}
    )
    
    return jsonify(stats)


# Health check
@team_bp.route('/teams/health', methods=['GET'])
def health_check():
    """Health check for team endpoints"""
    try:
        health_status = team_service.health_check()
        
        return jsonify({
            'status': 'healthy',
            'service': 'team',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })
        
    except Exception as e:
        logging_service.error(
            "TeamRoutes",
            "HEALTH_CHECK_ERROR",
            f"Health check error: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'team',
            'error': str(e)
        }), 500

