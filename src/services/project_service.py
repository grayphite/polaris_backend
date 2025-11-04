"""
ProjectService - Business logic for project management

Handles CRUD operations, soft deletes, and project recovery.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Optional, List

from sqlalchemy import or_, and_
from src.extensions import db
from src.models.project import Project, ProjectMember
from src.models.user import User
from src.models.team import TeamMember


logger = logging.getLogger(__name__)


@dataclass
class ProjectResult:
    """Result of a project operation"""
    success: bool
    project: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ProjectService:
    """Service for managing projects with full CRUD operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_project(self, name: str, user_id: int,
                      description: Optional[str] = None, is_public: bool = False) -> ProjectResult:
        """
        Create a new project
        
        Args:
            name: Name of the project
            user_id: ID of the user creating the project
            description: Optional project description
            is_public: Whether the project should be public (default: False)
            
        Returns:
            ProjectResult with success status and project data
        """
        try:
            # Validate input
            if not name or not name.strip():
                return ProjectResult(
                    success=False,
                    error="Project name is required"
                )
            
            if len(name) > 255:
                return ProjectResult(
                    success=False,
                    error="Project name must be less than 255 characters"
                )
            
            # Create project
            project = Project(
                name=name.strip(),
                description=description,
                created_by=user_id,
                is_deleted=False,
                is_public=is_public
            )
            
            db.session.add(project)
            db.session.flush()

            # Add creator as project owner member for parity with teams
            owner_member = ProjectMember(
                project_id=project.id,
                user_id=user_id,
                role='owner',
                added_by=user_id,
                is_deleted=False
            )
            db.session.add(owner_member)
            db.session.commit()
            
            self.logger.info(f"Project created: {project.id} by user {user_id}")
            
            return ProjectResult(
                success=True,
                project=project.to_dict(),
                message="Project created successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating project: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    # -------- Project membership management --------

    def _verify_project_management_access(self, project_id: int, user_id: int) -> bool:
        project = Project.query.filter_by(id=project_id, is_deleted=False).first()
        if not project:
            return False
        if project.created_by == user_id:
            return True
        member = project.get_member_by_user_id(user_id)
        return bool(member and member.can_manage_project())

    def add_project_member(self, project_id: int, user_id: int, member_user_id: int, role: str = 'member') -> ProjectResult:
        try:
            # Only project owner can add members
            project = Project.query.filter_by(id=project_id, is_deleted=False).first()
            if not project:
                return ProjectResult(success=False, error="Project not found")
            if project.created_by != user_id:
                return ProjectResult(success=False, error="Only project owner can add members")

            member_user = User.query.get(member_user_id)
            if not member_user:
                return ProjectResult(success=False, error="User not found")

            existing = ProjectMember.query.filter_by(project_id=project_id, user_id=member_user_id, is_deleted=False).first()
            if existing:
                return ProjectResult(success=False, error="User is already a member of this project")

            proj_member = ProjectMember(
                project_id=project_id,
                user_id=member_user_id,
                role=role,
                added_by=user_id,
                is_deleted=False
            )
            db.session.add(proj_member)
            db.session.commit()

            return ProjectResult(success=True, project=proj_member.to_dict(), message="Member added successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error adding project member: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def remove_project_member(self, project_id: int, user_id: int, member_user_id: int) -> ProjectResult:
        try:
            if not self._verify_project_management_access(project_id, user_id):
                return ProjectResult(success=False, error="Access denied")

            project = Project.query.get(project_id)
            if not project:
                return ProjectResult(success=False, error="Project not found")

            # Prevent removing project owner
            if project.created_by == member_user_id:
                return ProjectResult(success=False, error="Cannot remove project owner")

            member = ProjectMember.query.filter_by(project_id=project_id, user_id=member_user_id, is_deleted=False).first()
            if not member:
                return ProjectResult(success=False, error="Member not found")

            member.is_deleted = True
            member.left_at = datetime.now(UTC)
            member.removed_by = user_id
            member.updated_at = datetime.now(UTC)
            db.session.commit()
            return ProjectResult(success=True, message="Member removed successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error removing project member: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def list_project_members(self, project_id: int, user_id: int, page: int = 1, per_page: int = 20) -> Dict:
        try:
            project = Project.query.filter_by(id=project_id, is_deleted=False).first()
            if not project:
                return {'success': False, 'error': 'Project not found', 'members': [], 'pagination': {}}

            # Require at least membership or ownership to view
            if not (project.created_by == user_id or project.is_member(user_id)):
                return {'success': False, 'error': 'Access denied', 'members': [], 'pagination': {}}

            query = ProjectMember.query.filter_by(project_id=project_id, is_deleted=False).order_by(ProjectMember.joined_at.asc())
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            members = [m.to_summary_dict() for m in pagination.items]
            return {
                'success': True,
                'members': members,
                'pagination': {
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': page,
                    'per_page': per_page,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
        except Exception as e:
            error_msg = f"Error listing project members: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg, 'members': [], 'pagination': {}}

    def update_project_member_role(self, project_id: int, user_id: int, member_user_id: int, new_role: str) -> ProjectResult:
        try:
            if not self._verify_project_management_access(project_id, user_id):
                return ProjectResult(success=False, error="Access denied")

            project = Project.query.get(project_id)
            if not project:
                return ProjectResult(success=False, error="Project not found")

            if project.created_by == member_user_id:
                return ProjectResult(success=False, error="Cannot change project owner's role")

            member = ProjectMember.query.filter_by(project_id=project_id, user_id=member_user_id, is_deleted=False).first()
            if not member:
                return ProjectResult(success=False, error="Member not found")

            member.role = new_role
            member.updated_at = datetime.now(UTC)
            db.session.commit()
            return ProjectResult(success=True, project=member.to_dict(), message="Member role updated successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating project member role: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def get_project_by_id(self, project_id: int, user_id: int,
                         include_deleted: bool = False, team_id: Optional[int] = None) -> Optional[Dict]:
        """
        Get a specific project by ID
        
        Args:
            project_id: ID of the project
            user_id: ID of the requesting user
            include_deleted: Whether to include soft-deleted projects
            
        Returns:
            Project dictionary or None if not found
        """
        try:
            query = Project.query.filter_by(id=project_id, created_by=user_id)

            # Optional team filter: ensure project's creator is a member of the team
            if team_id:
                member_user_ids = db.session.query(TeamMember.user_id).filter(
                    TeamMember.team_id == team_id,
                    TeamMember.is_deleted == False
                )
                query = query.filter(Project.created_by.in_(member_user_ids))
            
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            
            project = query.first()
            
            return project.to_dict() if project else None
            
        except Exception as e:
            error_msg = f"Error fetching project: {str(e)}"
            self.logger.error(error_msg)
            return None

    def list_projects(self, user_id: int, page: int = 1, per_page: int = 20,
                     search: str = None, include_deleted: bool = False,
                     team_id: Optional[int] = None) -> Dict:
        """
        List projects with pagination and search
        
        Args:
            user_id: ID of the requesting user
            page: Page number (1-indexed)
            per_page: Items per page
            search: Optional search query
            include_deleted: Whether to include soft-deleted projects
            
        Returns:
            Dictionary with projects list and pagination metadata
        """
        try:
            query = Project.query.filter_by(created_by=user_id)

            # Optional team filter: only projects whose creator is member of team
            if team_id:
                member_user_ids = db.session.query(TeamMember.user_id).filter(
                    TeamMember.team_id == team_id,
                    TeamMember.is_deleted == False
                )
                query = query.filter(Project.created_by.in_(member_user_ids))
            
            # Filter deleted projects
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            
            # Search functionality
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Project.name.ilike(search_term),
                        Project.description.ilike(search_term)
                    )
                )
            
            # Order by created_at descending
            query = query.order_by(Project.created_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            projects = [project.to_summary_dict() for project in pagination.items]
            
            return {
                'success': True,
                'projects': projects,
                'pagination': {
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': page,
                    'per_page': per_page,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
            
        except Exception as e:
            error_msg = f"Error listing projects: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'projects': [],
                'pagination': {}
            }

    def list_public_projects(self, page: int = 1, per_page: int = 20,
                            search: str = None) -> Dict:
        """
        List all public projects with pagination and search
        
        Args:
            page: Page number (1-indexed)
            per_page: Items per page
            search: Optional search query
            
        Returns:
            Dictionary with projects list and pagination metadata
        """
        try:
            query = Project.query.filter_by(is_public=True, is_deleted=False)
            
            # Search functionality
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Project.name.ilike(search_term),
                        Project.description.ilike(search_term)
                    )
                )
            
            # Order by created_at descending
            query = query.order_by(Project.created_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            projects = [project.to_summary_dict() for project in pagination.items]
            
            return {
                'success': True,
                'projects': projects,
                'pagination': {
                    'total': pagination.total,
                    'pages': pagination.pages,
                    'current_page': page,
                    'per_page': per_page,
                    'has_next': pagination.has_next,
                    'has_prev': pagination.has_prev
                }
            }
            
        except Exception as e:
            error_msg = f"Error listing public projects: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'projects': [],
                'pagination': {}
            }

    def update_project(self, project_id: int, user_id: int,
                      data: Dict) -> ProjectResult:
        """
        Update an existing project
        
        Args:
            project_id: ID of the project to update
            user_id: ID of the requesting user
            data: Dictionary with fields to update
            
        Returns:
            ProjectResult with updated project data
        """
        try:
            project = Project.query.filter_by(
                id=project_id,
                created_by=user_id,
                is_deleted=False
            ).first()
            
            if not project:
                return ProjectResult(
                    success=False,
                    error="Project not found or access denied"
                )
            
            # Update allowed fields
            if 'name' in data:
                if not data['name'] or not data['name'].strip():
                    return ProjectResult(
                        success=False,
                        error="Project name cannot be empty"
                    )
                project.name = data['name'].strip()
            
            if 'description' in data:
                project.description = data.get('description')
            
            project.updated_at = datetime.now(UTC)
            db.session.commit()
            
            self.logger.info(f"Project updated: {project.id} by user {user_id}")
            
            return ProjectResult(
                success=True,
                project=project.to_dict(),
                message="Project updated successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating project: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def delete_project(self, project_id: int, user_id: int) -> ProjectResult:
        """
        Soft delete a project
        
        Args:
            project_id: ID of the project to delete
            user_id: ID of the user deleting the project
            
        Returns:
            ProjectResult indicating success or failure
        """
        try:
            project = Project.query.filter_by(
                id=project_id,
                created_by=user_id,
                is_deleted=False
            ).first()
            
            if not project:
                return ProjectResult(
                    success=False,
                    error="Project not found or already deleted"
                )
            
            # Soft delete
            project.is_deleted = True
            project.deleted_at = datetime.now(UTC)
            project.deleted_by = user_id
            project.updated_at = datetime.now(UTC)
            
            # Cascade: soft delete all associated chats
            from src.models.chat import Chat
            cascade_count = 0
            for chat in project.chats.filter_by(is_deleted=False):
                chat.is_deleted = True
                chat.deleted_at = datetime.now(UTC)
                chat.deleted_by = user_id
                chat.updated_at = datetime.now(UTC)
                cascade_count += 1
            
            db.session.commit()
            
            self.logger.info(
                f"Project soft-deleted: {project.id} by user {user_id}. "
                f"Cascade deleted {cascade_count} chats"
            )
            
            return ProjectResult(
                success=True,
                message="Project deleted successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting project: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def restore_project(self, project_id: int, user_id: int) -> ProjectResult:
        """
        Restore a soft-deleted project
        
        Args:
            project_id: ID of the project to restore
            user_id: ID of the requesting user
            
        Returns:
            ProjectResult with restored project data
        """
        try:
            project = Project.query.filter_by(
                id=project_id,
                created_by=user_id,
                is_deleted=True
            ).first()
            
            if not project:
                return ProjectResult(
                    success=False,
                    error="Project not found or not deleted"
                )
            
            # Restore project
            project.is_deleted = False
            project.deleted_at = None
            project.deleted_by = None
            project.updated_at = datetime.now(UTC)
            
            # Cascade: restore all associated chats
            from src.models.chat import Chat
            cascade_count = 0
            for chat in project.chats.filter_by(is_deleted=True):
                chat.is_deleted = False
                chat.deleted_at = None
                chat.deleted_by = None
                chat.updated_at = datetime.now(UTC)
                cascade_count += 1
            
            db.session.commit()
            
            self.logger.info(
                f"Project restored: {project.id} by user {user_id}. "
                f"Cascade restored {cascade_count} chats"
            )
            
            return ProjectResult(
                success=True,
                project=project.to_dict(),
                message="Project restored successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error restoring project: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def permanent_delete_project(self, project_id: int, user_id: int) -> ProjectResult:
        """
        Permanently delete a project (use with caution)
        
        Args:
            project_id: ID of the project to permanently delete
            user_id: ID of the requesting user
            
        Returns:
            ProjectResult indicating success or failure
        """
        try:
            project = Project.query.filter_by(
                id=project_id,
                created_by=user_id
            ).first()
            
            if not project:
                return ProjectResult(
                    success=False,
                    error="Project not found"
                )
            
            # Permanent deletion
            db.session.delete(project)
            db.session.commit()
            
            self.logger.warning(
                f"Project permanently deleted: {project.id} by user {user_id}"
            )
            
            return ProjectResult(
                success=True,
                message="Project permanently deleted"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error permanently deleting project: {str(e)}"
            self.logger.error(error_msg)
            return ProjectResult(success=False, error=error_msg)

    def get_project_statistics(self, user_id: int) -> Dict:
        """
        Get statistics about user's projects
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with project statistics
        """
        try:
            total_projects = Project.query.filter_by(
                created_by=user_id
            ).count()
            
            active_projects = Project.query.filter_by(
                created_by=user_id,
                is_deleted=False
            ).count()
            
            deleted_projects = Project.query.filter_by(
                created_by=user_id,
                is_deleted=True
            ).count()
            
            # Most recent project
            recent_project = Project.query.filter_by(
                created_by=user_id,
                is_deleted=False
            ).order_by(Project.created_at.desc()).first()
            
            return {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'deleted_projects': deleted_projects,
                'most_recent': recent_project.to_summary_dict() if recent_project else None
            }
            
        except Exception as e:
            error_msg = f"Error getting statistics: {str(e)}"
            self.logger.error(error_msg)
            return {
                'total_projects': 0,
                'active_projects': 0,
                'deleted_projects': 0,
                'most_recent': None,
                'error': error_msg
            }

    def health_check(self) -> Dict:
        """
        Health check for project service
        
        Returns:
            Dictionary with health status
        """
        try:
            # Test database connectivity
            project_count = Project.query.count()
            
            return {
                'status': 'healthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'total_projects_in_system': project_count
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'error': str(e)
            }


# Global instance
project_service = ProjectService()

