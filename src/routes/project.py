"""
Routes for Project management

Handles all HTTP endpoints for project CRUD operations with
authentication, validation, and audit logging.
"""

from functools import wraps
from flask import Blueprint, request, jsonify, g

from src.services.auth_service import auth_service
from src.services.project_service import project_service
from src.services.logging_service import logging_service, ActionType, log_action


project_bp = Blueprint('project', __name__)


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
                    "ProjectRoutes",
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
                "ProjectRoutes",
                func.__name__.upper(),
                f"Validation error: {str(e)}"
            )
            return jsonify({'error': str(e)}), 400
        except PermissionError as e:
            logging_service.warning(
                "ProjectRoutes",
                func.__name__.upper(),
                f"Permission denied: {str(e)}"
            )
            return jsonify({'error': 'Access denied'}), 403
        except FileNotFoundError as e:
            logging_service.warning(
                "ProjectRoutes",
                func.__name__.upper(),
                f"Resource not found: {str(e)}"
            )
            return jsonify({'error': 'Resource not found'}), 404
        except Exception as e:
            logging_service.error(
                "ProjectRoutes",
                func.__name__.upper(),
                f"Internal error: {str(e)}",
                error_details={'error': str(e)}
            )
            return jsonify({'error': 'Internal server error'}), 500
    
    return wrapper


def get_current_user():
    """Get current authenticated user from Flask g object"""
    return getattr(g, 'current_user', None)


@project_bp.route('/projects', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "project")
def list_projects():
    """
    List projects with pagination and search
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    - include_deleted: Include soft-deleted projects (default: false)
    """
    current_user = get_current_user()
    
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
    team_id = request.args.get('team_id', type=int)
    
    # Fetch from service
    result = project_service.list_projects(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        search=search,
        include_deleted=include_deleted,
        team_id=team_id
    )
    
    logging_service.info(
        "ProjectRoutes",
        "GET_PROJECTS",
        f"Projects listed for user {current_user.id}",
        user_id=current_user.id,
        metadata={
            'page': page,
            'per_page': per_page,
            'search': search,
            'total_found': result.get('pagination', {}).get('total', 0),
            'team_id': team_id
        }
    )
    
    return jsonify(result)


@project_bp.route('/public-projects', methods=['GET'])
@handle_errors
@log_action(ActionType.READ, "public_projects")
def list_public_projects():
    """
    List all public projects with pagination and search
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    - search: Search query
    """
    # Parse query parameters
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)
    search = request.args.get('search', '').strip()
    
    # Fetch from service
    result = project_service.list_public_projects(
        page=page,
        per_page=per_page,
        search=search
    )
    
    logging_service.info(
        "ProjectRoutes",
        "GET_PUBLIC_PROJECTS",
        f"Public projects listed",
        metadata={
            'page': page,
            'per_page': per_page,
            'search': search,
            'total_found': result.get('pagination', {}).get('total', 0)
        }
    )
    
    return jsonify(result)


@project_bp.route('/projects/<int:project_id>', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "project")
def get_project(project_id):
    """Get a specific project by ID"""
    current_user = get_current_user()
    
    # Fetch from service
    team_id = request.args.get('team_id', type=int)

    project = project_service.get_project_by_id(
        project_id=project_id,
        user_id=current_user.id,
        team_id=team_id
    )
    
    if not project:
        raise FileNotFoundError("Project not found")
    
    logging_service.info(
        "ProjectRoutes",
        "GET_PROJECT",
        f"Project {project_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id, 'team_id': team_id}
    )
    
    return jsonify(project)


@project_bp.route('/projects', methods=['POST'])
@auth_service.require_auth
@validate_request_data(
    required_fields=['name'],
    optional_fields=['description', 'is_public']
)
@handle_errors
@log_action(ActionType.CREATE, "project")
def create_project():
    """Create a new project"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Create project via service
    result = project_service.create_project(
        name=data['name'],
        user_id=current_user.id,
        description=data.get('description'),
        is_public=data.get('is_public', False)
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="project",
        resource_id=str(result.project['id']),
        new_values=result.project,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'name': result.project['name']}
    )
    
    logging_service.info(
        "ProjectRoutes",
        "CREATE_PROJECT",
        f"Project created: {result.project['name']} by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': result.project['id']}
    )
    
    return jsonify(result.project), 201


@project_bp.route('/projects/<int:project_id>', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(
    optional_fields=['name', 'description']
)
@handle_errors
@log_action(ActionType.UPDATE, "project")
def update_project(project_id):
    """Update an existing project"""
    current_user = get_current_user()
    data = request.validated_data
    
    # Get old values for audit
    old_project = project_service.get_project_by_id(project_id, current_user.id)
    if not old_project:
        raise FileNotFoundError("Project not found")
    
    # Update via service
    result = project_service.update_project(
        project_id=project_id,
        user_id=current_user.id,
        data=data
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="project",
        resource_id=str(project_id),
        old_values=old_project,
        new_values=result.project,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'fields_updated': list(data.keys())}
    )
    
    logging_service.info(
        "ProjectRoutes",
        "UPDATE_PROJECT",
        f"Project {project_id} updated by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id}
    )
    
    return jsonify(result.project)


@project_bp.route('/projects/<int:project_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "project")
def delete_project(project_id):
    """Soft delete a project"""
    current_user = get_current_user()
    
    # Get project for audit
    project = project_service.get_project_by_id(project_id, current_user.id)
    if not project:
        raise FileNotFoundError("Project not found")
    
    # Delete via service
    result = project_service.permanent_delete_project(
        project_id=project_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="project",
        resource_id=str(project_id),
        old_values=project,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'name': project['name']}
    )
    
    logging_service.info(
        "ProjectRoutes",
        "DELETE_PROJECT",
        f"Project {project_id} deleted by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id}
    )
    
    return jsonify({'message': 'Project deleted successfully'})


@project_bp.route('/projects/<int:project_id>/restore', methods=['POST'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.UPDATE, "project")
def restore_project(project_id):
    """Restore a soft-deleted project"""
    current_user = get_current_user()
    
    # Restore via service
    result = project_service.restore_project(
        project_id=project_id,
        user_id=current_user.id
    )
    
    if not result.success:
        return jsonify({'error': result.error}), 400
    
    # Audit log
    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="project",
        resource_id=str(project_id),
        new_values=result.project,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'action': 'restore', 'name': result.project['name']}
    )
    
    logging_service.info(
        "ProjectRoutes",
        "RESTORE_PROJECT",
        f"Project {project_id} restored by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id}
    )
    
    return jsonify(result.project)


@project_bp.route('/projects/stats', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "project_stats")
def get_project_stats():
    """Get project statistics for current user"""
    current_user = get_current_user()
    
    # Get stats from service
    stats = project_service.get_project_statistics(current_user.id)
    
    logging_service.info(
        "ProjectRoutes",
        "GET_STATS",
        f"Statistics accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'total_projects': stats.get('total_projects', 0)}
    )
    
    return jsonify(stats)


# Health check
@project_bp.route('/projects/health', methods=['GET'])
def health_check():
    """Health check for project endpoints"""
    try:
        health_status = project_service.health_check()
        
        return jsonify({
            'status': 'healthy',
            'service': 'project',
            'timestamp': health_status.get('timestamp'),
            'details': health_status
        })
        
    except Exception as e:
        logging_service.error(
            "ProjectRoutes",
            "HEALTH_CHECK_ERROR",
            f"Health check error: {str(e)}"
        )
        return jsonify({
            'status': 'unhealthy',
            'service': 'project',
            'error': str(e)
        }), 500


# -------- Project Members Endpoints --------

@project_bp.route('/projects/<int:project_id>/members', methods=['GET'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.READ, "project_members")
def list_project_members(project_id):
    """List members of a project
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 10, max: 100)
    
    Authorization: Bearer token (must be project owner or member)
    """
    current_user = get_current_user()
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 10, type=int), 100)

    result = project_service.list_project_members(
        project_id=project_id,
        user_id=current_user.id,
        page=page,
        per_page=per_page
    )

    logging_service.info(
        "ProjectRoutes",
        "GET_PROJECT_MEMBERS",
        f"Project members for project {project_id} accessed by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id, 'total_found': result.get('pagination', {}).get('total', 0)}
    )

    return jsonify(result)


@project_bp.route('/projects/<int:project_id>/members', methods=['POST'])
@auth_service.require_auth
@validate_request_data(required_fields=['user_id'], optional_fields=['role'])
@handle_errors
@log_action(ActionType.CREATE, "project_member")
def add_project_member(project_id):
    """Add a member to a project
    
    Request body (JSON):
    - user_id: integer (required)
    - role: "member" or "admin" (default: "member")
    
    Authorization: Bearer token (project owner or admin)
    """
    current_user = get_current_user()
    data = request.validated_data

    result = project_service.add_project_member(
        project_id=project_id,
        user_id=current_user.id,
        member_user_id=data['user_id'],
        role=data.get('role', 'member')
    )

    if not result.success:
        return jsonify({'error': result.error}), 400

    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.CREATE,
        resource_type="project_member",
        resource_id=str(result.project.get('id')),
        new_values=result.project,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'project_id': project_id, 'member_user_id': data['user_id'], 'role': data.get('role', 'member')}
    )

    logging_service.info(
        "ProjectRoutes",
        "ADD_PROJECT_MEMBER",
        f"Member added to project {project_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id, 'member_user_id': data['user_id']}
    )

    return jsonify(result.project), 201


@project_bp.route('/projects/<int:project_id>/members/<int:member_user_id>', methods=['DELETE'])
@auth_service.require_auth
@handle_errors
@log_action(ActionType.DELETE, "project_member")
def remove_project_member(project_id, member_user_id):
    """Remove a member from a project
    
    Path params:
    - member_user_id: integer (user id to remove)
    
    Authorization: Bearer token (project owner or admin)
    """
    current_user = get_current_user()

    result = project_service.remove_project_member(
        project_id=project_id,
        user_id=current_user.id,
        member_user_id=member_user_id
    )

    if not result.success:
        return jsonify({'error': result.error}), 400

    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.DELETE,
        resource_type="project_member",
        resource_id=f"{project_id}_{member_user_id}",
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'project_id': project_id, 'member_user_id': member_user_id}
    )

    logging_service.info(
        "ProjectRoutes",
        "REMOVE_PROJECT_MEMBER",
        f"Member removed from project {project_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id, 'member_user_id': member_user_id}
    )

    return jsonify({'message': 'Member removed successfully'})


@project_bp.route('/projects/<int:project_id>/members/<int:member_user_id>/role', methods=['PUT'])
@auth_service.require_auth
@validate_request_data(required_fields=['role'])
@handle_errors
@log_action(ActionType.UPDATE, "project_member_role")
def update_project_member_role(project_id, member_user_id):
    """Update a project member's role
    
    Request body (JSON):
    - role: "member" or "admin" (required)
    
    Authorization: Bearer token (project owner or admin)
    """
    current_user = get_current_user()
    data = request.validated_data

    result = project_service.update_project_member_role(
        project_id=project_id,
        user_id=current_user.id,
        member_user_id=member_user_id,
        new_role=data['role']
    )

    if not result.success:
        return jsonify({'error': result.error}), 400

    logging_service.audit(
        user_id=current_user.id,
        action_type=ActionType.UPDATE,
        resource_type="project_member_role",
        resource_id=f"{project_id}_{member_user_id}",
        new_values={'role': data['role']},
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        metadata={'project_id': project_id, 'member_user_id': member_user_id, 'new_role': data['role']}
    )

    logging_service.info(
        "ProjectRoutes",
        "UPDATE_PROJECT_MEMBER_ROLE",
        f"Member role updated in project {project_id} by user {current_user.id}",
        user_id=current_user.id,
        metadata={'project_id': project_id, 'member_user_id': member_user_id, 'new_role': data['role']}
    )

    return jsonify(result.project)
