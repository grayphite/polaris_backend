"""
TeamService - Business logic for team management

Handles CRUD operations for teams and team members with proper
access control and member management.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Optional, List

from sqlalchemy import or_, and_
from src.extensions import db
from src.models.team import Team, TeamMember
from src.models.user import User


logger = logging.getLogger(__name__)


@dataclass
class TeamResult:
    """Result of a team operation"""
    success: bool
    team: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


@dataclass
class TeamMemberResult:
    """Result of a team member operation"""
    success: bool
    member: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


class TeamService:
    """Service for managing teams and team members with full CRUD operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def _verify_team_access(self, team_id: int, user_id: int) -> Optional[Team]:
        """
        Verify user has access to the team (either owns it or is a member)
        
        Args:
            team_id: ID of the team
            user_id: ID of the user
            
        Returns:
            Team object if user has access, None otherwise
        """
        team = Team.query.filter_by(
            id=team_id,
            is_deleted=False
        ).first()
        
        if not team:
            return None
        
        # Allow access if user owns the team OR is a member
        if team.created_by == user_id:
            return team
        
        # Check if user is a member
        member = team.get_member_by_user_id(user_id)
        if member:
            return team
        
        return None

    def _verify_team_management_access(self, team_id: int, user_id: int) -> Optional[Team]:
        """
        Verify user can manage the team (owner or admin)
        
        Args:
            team_id: ID of the team
            user_id: ID of the user
            
        Returns:
            Team object if user can manage, None otherwise
        """
        team = self._verify_team_access(team_id, user_id)
        if not team:
            return None
        
        # Owner can always manage
        if team.created_by == user_id:
            return team
        
        # Check if user is admin
        member = team.get_member_by_user_id(user_id)
        if member and member.can_manage_team():
            return team
        
        return None

    def create_team(self, name: str, user_id: int,
                   description: Optional[str] = None) -> TeamResult:
        """
        Create a new team
        
        Args:
            name: Name of the team
            user_id: ID of the user creating the team
            description: Optional team description
            
        Returns:
            TeamResult with success status and team data
        """
        try:
            # Validate input
            if not name or not name.strip():
                return TeamResult(
                    success=False,
                    error="Team name is required"
                )
            
            if len(name) > 255:
                return TeamResult(
                    success=False,
                    error="Team name must be less than 255 characters"
                )
            
            # Create team
            team = Team(
                name=name.strip(),
                description=description,
                created_by=user_id,
                is_deleted=False
            )
            
            db.session.add(team)
            db.session.flush()  # Get the team ID
            
            # Add creator as owner member
            owner_member = TeamMember(
                team_id=team.id,
                user_id=user_id,
                role='owner',
                added_by=user_id,
                is_deleted=False
            )
            
            db.session.add(owner_member)
            db.session.commit()
            
            self.logger.info(f"Team created: {team.id} by user {user_id}")
            
            return TeamResult(
                success=True,
                team=team.to_dict(),
                message="Team created successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating team: {str(e)}"
            self.logger.error(error_msg)
            return TeamResult(success=False, error=error_msg)

    def get_team_by_id(self, team_id: int, user_id: int,
                       include_deleted: bool = False) -> Optional[Dict]:
        """
        Get a specific team by ID
        
        Args:
            team_id: ID of the team
            user_id: ID of the requesting user
            include_deleted: Whether to include soft-deleted teams
            
        Returns:
            Team dictionary or None if not found
        """
        try:
            team = Team.query.filter_by(id=team_id)
            
            if not include_deleted:
                team = team.filter_by(is_deleted=False)
            
            team = team.first()
            
            if not team:
                return None
            
            # Verify user has access
            if not self._verify_team_access(team_id, user_id):
                return None
            
            return team.to_dict()
            
        except Exception as e:
            error_msg = f"Error fetching team: {str(e)}"
            self.logger.error(error_msg)
            return None

    def list_teams(self, user_id: int, page: int = 1, per_page: int = 20,
                   search: str = None, include_deleted: bool = False) -> Dict:
        """
        List teams where user is owner or member
        
        Args:
            user_id: ID of the requesting user
            page: Page number (1-indexed)
            per_page: Items per page
            search: Optional search query
            include_deleted: Whether to include soft-deleted teams
            
        Returns:
            Dictionary with teams list and pagination metadata
        """
        try:
            # Start with teams where user is owner or member
            query = Team.query.join(TeamMember).filter(
                or_(
                    Team.created_by == user_id,  # User's own teams
                    TeamMember.user_id == user_id  # Teams where user is member
                )
            )
            
            # Filter deleted teams
            if not include_deleted:
                query = query.filter(Team.is_deleted == False)
            
            # Search functionality
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Team.name.ilike(search_term),
                        Team.description.ilike(search_term)
                    )
                )
            
            # Order by created_at descending
            query = query.order_by(Team.created_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            teams = [team.to_summary_dict() for team in pagination.items]
            
            return {
                'success': True,
                'teams': teams,
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
            error_msg = f"Error listing teams: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'teams': [],
                'pagination': {}
            }

    def update_team(self, team_id: int, user_id: int,
                    data: Dict) -> TeamResult:
        """
        Update an existing team
        
        Args:
            team_id: ID of the team to update
            user_id: ID of the requesting user
            data: Dictionary with fields to update
            
        Returns:
            TeamResult with updated team data
        """
        try:
            team = Team.query.filter_by(
                id=team_id,
                is_deleted=False
            ).first()
            
            if not team:
                return TeamResult(
                    success=False,
                    error="Team not found"
                )
            
            # Verify user can manage the team
            if not self._verify_team_management_access(team_id, user_id):
                return TeamResult(
                    success=False,
                    error="Access denied"
                )
            
            # Update allowed fields
            if 'name' in data:
                if not data['name'] or not data['name'].strip():
                    return TeamResult(
                        success=False,
                        error="Team name cannot be empty"
                    )
                team.name = data['name'].strip()
            
            if 'description' in data:
                team.description = data.get('description')
            
            team.updated_at = datetime.now(UTC)
            db.session.commit()
            
            self.logger.info(f"Team updated: {team.id} by user {user_id}")
            
            return TeamResult(
                success=True,
                team=team.to_dict(),
                message="Team updated successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating team: {str(e)}"
            self.logger.error(error_msg)
            return TeamResult(success=False, error=error_msg)

    def delete_team(self, team_id: int, user_id: int) -> TeamResult:
        """
        Soft delete a team
        
        Args:
            team_id: ID of the team to delete
            user_id: ID of the user deleting the team
            
        Returns:
            TeamResult indicating success or failure
        """
        try:
            team = Team.query.filter_by(
                id=team_id,
                is_deleted=False
            ).first()
            
            if not team:
                return TeamResult(
                    success=False,
                    error="Team not found or already deleted"
                )
            
            # Only owner can delete team
            if team.created_by != user_id:
                return TeamResult(
                    success=False,
                    error="Only team owner can delete the team"
                )
            
            # Soft delete team
            team.is_deleted = True
            team.deleted_at = datetime.now(UTC)
            team.deleted_by = user_id
            team.updated_at = datetime.now(UTC)
            
            # Soft delete all team members
            for member in team.members.filter_by(is_deleted=False):
                member.is_deleted = True
                member.left_at = datetime.now(UTC)
                member.removed_by = user_id
                member.updated_at = datetime.now(UTC)
            
            db.session.commit()
            
            self.logger.info(f"Team soft-deleted: {team.id} by user {user_id}")
            
            return TeamResult(
                success=True,
                message="Team deleted successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting team: {str(e)}"
            self.logger.error(error_msg)
            return TeamResult(success=False, error=error_msg)

    def add_team_member(self, team_id: int, user_id: int, 
                       member_user_id: int, role: str = 'member',
                       added_by: int = None) -> TeamMemberResult:
        """
        Add a member to a team
        
        Args:
            team_id: ID of the team
            user_id: ID of the user requesting the addition
            member_user_id: ID of the user to add
            role: Role for the new member (default: 'member')
            added_by: ID of the user who added the member (defaults to user_id)
            
        Returns:
            TeamMemberResult with success status and member data
        """
        try:
            # Verify user can manage the team
            if not self._verify_team_management_access(team_id, user_id):
                return TeamMemberResult(
                    success=False,
                    error="Access denied"
                )
            
            # Check if user exists
            member_user = User.query.get(member_user_id)
            if not member_user:
                return TeamMemberResult(
                    success=False,
                    error="User not found"
                )
            
            # Check if user is already a member
            existing_member = TeamMember.query.filter_by(
                team_id=team_id,
                user_id=member_user_id,
                is_deleted=False
            ).first()
            
            if existing_member:
                return TeamMemberResult(
                    success=False,
                    error="User is already a member of this team"
                )
            
            # Create team member
            team_member = TeamMember(
                team_id=team_id,
                user_id=member_user_id,
                role=role,
                added_by=added_by or user_id,
                is_deleted=False
            )
            
            db.session.add(team_member)
            db.session.commit()
            
            self.logger.info(f"Member added to team {team_id}: user {member_user_id} by user {user_id}")
            
            return TeamMemberResult(
                success=True,
                member=team_member.to_dict(),
                message="Member added successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error adding team member: {str(e)}"
            self.logger.error(error_msg)
            return TeamMemberResult(success=False, error=error_msg)

    def remove_team_member(self, team_id: int, user_id: int,
                          member_user_id: int) -> TeamMemberResult:
        """
        Remove a member from a team
        
        Args:
            team_id: ID of the team
            user_id: ID of the user requesting the removal
            member_user_id: ID of the user to remove
            
        Returns:
            TeamMemberResult indicating success or failure
        """
        try:
            # Verify user can manage the team
            if not self._verify_team_management_access(team_id, user_id):
                return TeamMemberResult(
                    success=False,
                    error="Access denied"
                )
            
            # Find the member
            member = TeamMember.query.filter_by(
                team_id=team_id,
                user_id=member_user_id,
                is_deleted=False
            ).first()
            
            if not member:
                return TeamMemberResult(
                    success=False,
                    error="Member not found"
                )
            
            # Prevent removing team owner
            team = Team.query.get(team_id)
            if team and team.created_by == member_user_id:
                return TeamMemberResult(
                    success=False,
                    error="Cannot remove team owner"
                )
            
            # Soft delete member
            member.is_deleted = True
            member.left_at = datetime.now(UTC)
            member.removed_by = user_id
            member.updated_at = datetime.now(UTC)
            
            db.session.commit()
            
            self.logger.info(f"Member removed from team {team_id}: user {member_user_id} by user {user_id}")
            
            return TeamMemberResult(
                success=True,
                message="Member removed successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error removing team member: {str(e)}"
            self.logger.error(error_msg)
            return TeamMemberResult(success=False, error=error_msg)

    def list_team_members(self, team_id: int, user_id: int,
                          page: int = 1, per_page: int = 20) -> Dict:
        """
        List all members of a team
        
        Args:
            team_id: ID of the team
            user_id: ID of the requesting user
            page: Page number
            per_page: Items per page
            
        Returns:
            Dictionary with members list and pagination metadata
        """
        try:
            # Verify user has access to the team
            if not self._verify_team_access(team_id, user_id):
                return {
                    'success': False,
                    'error': 'Team not found or access denied',
                    'members': [],
                    'pagination': {}
                }
            
            # Query team members
            query = TeamMember.query.filter_by(
                team_id=team_id,
                is_deleted=False
            )
            
            # Order by joined_at ascending
            query = query.order_by(TeamMember.joined_at.asc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            members = [member.to_summary_dict() for member in pagination.items]
            
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
            error_msg = f"Error listing team members: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'members': [],
                'pagination': {}
            }

    def update_team_member_role(self, team_id: int, user_id: int,
                               member_user_id: int, new_role: str) -> TeamMemberResult:
        """
        Update a team member's role
        
        Args:
            team_id: ID of the team
            user_id: ID of the user requesting the update
            member_user_id: ID of the member to update
            new_role: New role for the member
            
        Returns:
            TeamMemberResult with updated member data
        """
        try:
            # Verify user can manage the team
            if not self._verify_team_management_access(team_id, user_id):
                return TeamMemberResult(
                    success=False,
                    error="Access denied"
                )
            
            # Find the member
            member = TeamMember.query.filter_by(
                team_id=team_id,
                user_id=member_user_id,
                is_deleted=False
            ).first()
            
            if not member:
                return TeamMemberResult(
                    success=False,
                    error="Member not found"
                )
            
            # Prevent changing team owner's role
            team = Team.query.get(team_id)
            if team and team.created_by == member_user_id:
                return TeamMemberResult(
                    success=False,
                    error="Cannot change team owner's role"
                )
            
            # Update role
            member.role = new_role
            member.updated_at = datetime.now(UTC)
            
            db.session.commit()
            
            self.logger.info(f"Member role updated in team {team_id}: user {member_user_id} to {new_role} by user {user_id}")
            
            return TeamMemberResult(
                success=True,
                member=member.to_dict(),
                message="Member role updated successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating member role: {str(e)}"
            self.logger.error(error_msg)
            return TeamMemberResult(success=False, error=error_msg)

    def get_team_statistics(self, user_id: int) -> Dict:
        """
        Get statistics about user's teams
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with team statistics
        """
        try:
            # Teams owned by user
            owned_teams = Team.query.filter_by(
                created_by=user_id,
                is_deleted=False
            ).count()
            
            # Teams where user is a member
            member_teams = TeamMember.query.filter_by(
                user_id=user_id,
                is_deleted=False
            ).count()
            
            # Total teams user has access to
            total_teams = owned_teams + member_teams
            
            # Most recent team
            recent_team = Team.query.join(TeamMember).filter(
                or_(
                    Team.created_by == user_id,
                    TeamMember.user_id == user_id
                ),
                Team.is_deleted == False
            ).order_by(Team.created_at.desc()).first()
            
            return {
                'total_teams': total_teams,
                'owned_teams': owned_teams,
                'member_teams': member_teams,
                'most_recent': recent_team.to_summary_dict() if recent_team else None
            }
            
        except Exception as e:
            error_msg = f"Error getting statistics: {str(e)}"
            self.logger.error(error_msg)
            return {
                'total_teams': 0,
                'owned_teams': 0,
                'member_teams': 0,
                'most_recent': None,
                'error': error_msg
            }

    def health_check(self) -> Dict:
        """
        Health check for team service
        
        Returns:
            Dictionary with health status
        """
        try:
            # Test database connectivity
            team_count = Team.query.count()
            member_count = TeamMember.query.count()
            
            return {
                'status': 'healthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'total_teams_in_system': team_count,
                'total_members_in_system': member_count
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'error': str(e)
            }


# Global instance
team_service = TeamService()

