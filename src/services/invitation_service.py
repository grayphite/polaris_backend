"""
InvitationService - Business logic for team invitation management

Handles invitation creation, acceptance, decline, cancellation,
and comprehensive invitation lifecycle management.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Optional, List

from sqlalchemy import or_, and_
from src.extensions import db
from src.models.invitation import Invitation
from src.models.team import Team, TeamMember
from src.models.user import User
from src.services.team_service import team_service
from src.services.email_service import email_service
from src.services.payment_services.usage_billing_service import UsageBillingService


logger = logging.getLogger(__name__)


@dataclass
class InvitationResult:
    """Result of an invitation operation"""
    success: bool
    invitation: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None
    # Optional overage/billing preview surfaced at invitation time (no charge yet)
    billing_intent: Optional[Dict] = None
    overage_preview: Optional[Dict] = None


class InvitationService:
    """Service for managing team invitations with full lifecycle operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def _verify_invitation_permission(self, team_id: int, user_id: int) -> Optional[Team]:
        """
        Verify user can send invitations for the team
        
        Args:
            team_id: ID of the team
            user_id: ID of the user
            
        Returns:
            Team object if user can invite, None otherwise
        """
        team = Team.query.filter_by(
            id=team_id,
            is_deleted=False
        ).first()
        
        if not team:
            return None
        
        # Owner can always invite
        if team.created_by == user_id:
            return team
        
        # Check if user is admin and can add members
        member = team.get_member_by_user_id(user_id)
        if member and member.can_add_members():
            return team
        
        return None

    def create_invitation(self, team_id: int, inviter_id: int, invited_email: str,
                         role: str = 'member', message: str = None,
                         expires_in_days: int = 7) -> InvitationResult:
        """
        Create a new team invitation
        
        Args:
            team_id: ID of the team
            inviter_id: ID of the user sending the invitation
            invited_email: Email of the invited user
            role: Role to assign to the invited user
            message: Optional invitation message
            expires_in_days: Days until invitation expires
            
        Returns:
            InvitationResult with success status and invitation data
        """
        try:
            # Validate input
            if not invited_email or not invited_email.strip():
                return InvitationResult(
                    success=False,
                    error="Invited email is required"
                )
            
            # Normalize email
            invited_email = invited_email.lower().strip()
            
            # Validate email format (basic check)
            if '@' not in invited_email or '.' not in invited_email.split('@')[1]:
                return InvitationResult(
                    success=False,
                    error="Invalid email format"
                )
            
            # Verify user can invite to this team
            team = self._verify_invitation_permission(team_id, inviter_id)
            if not team:
                return InvitationResult(
                    success=False,
                    error="Access denied or team not found"
                )
            
            # Check if invited email is already registered in the system
            invited_user = User.query.filter_by(email=invited_email).first()
            if invited_user:
                # User is already registered - check if already a member
                existing_member = TeamMember.query.filter_by(
                    team_id=team_id,
                    user_id=invited_user.id,
                    is_deleted=False
                ).first()
                
                if existing_member:
                    return InvitationResult(
                        success=False,
                        error="User is already a member of this team"
                    )
                
                # User exists but not a member - return error (don't send invitation email)
                return InvitationResult(
                    success=False,
                    error="This User is already registered in the system. Please add different email to invite peaple in the system."
                )
            
            # Check for existing pending invitation
            existing_invitation = Invitation.query.filter_by(
                team_id=team_id,
                invited_email=invited_email,
                status='pending',
                is_deleted=False
            ).filter(Invitation.expires_at > datetime.now(UTC)).first()
            
            if existing_invitation:
                return InvitationResult(
                    success=False,
                    error="A pending invitation already exists for this email"
                )
            
            # Calculate overage preview BEFORE creating invitation (no charge here)
            billing_intent = None
            overage_preview = None
            try:
                info = UsageBillingService.calculate_team_member_overage(team_id)
                if info is not None:
                    will_be_overage = info.current_active_members >= info.included_members_in_plan
                    overage_preview = {
                        'will_be_overage_if_accepted': will_be_overage,
                        'current_active_members': info.current_active_members,
                        'included_members_in_plan': info.included_members_in_plan,
                        'additional_member_cost_cents': info.additional_member_cost_cents,
                        'currency': info.currency,
                    }
                    if will_be_overage:
                        billing_intent = {
                            'action': 'increase_subscription_quantity_on_accept',
                            'additional_member_cost_cents': info.additional_member_cost_cents,
                            'currency': info.currency,
                            'message': 'Invite will cause overage when accepted; extra seat will be billed next invoice.'
                        }
            except Exception:
                # Do not block invitation if preview fails
                pass

            # Create invitation
            invitation = Invitation.create_invitation(
                team_id=team_id,
                inviter_id=inviter_id,
                invited_email=invited_email,
                role=role,
                message=message,
                expires_in_days=expires_in_days
            )
            
            db.session.add(invitation)
            db.session.commit()
            
            # Send invitation email
            self._send_invitation_email(invitation, team)
            
            self.logger.info(f"Invitation created: {invitation.id} for team {team_id} by user {inviter_id}")
            
            inv_dict = invitation.to_dict()
            if overage_preview is not None:
                inv_dict['overage_preview'] = overage_preview
            return InvitationResult(
                success=True,
                invitation=inv_dict,
                message="Invitation sent successfully",
                billing_intent=billing_intent,
                overage_preview=overage_preview
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)

    def get_invitation_by_token(self, token: str) -> Optional[Dict]:
        """
        Get invitation by token
        
        Args:
            token: Invitation token
            
        Returns:
            Invitation dictionary or None if not found
        """
        try:
            invitation = Invitation.get_by_token(token)
            
            if not invitation:
                return None
            
            # Auto-expire if needed
            if invitation.is_expired():
                invitation.expire()
                db.session.commit()
            
            return invitation.to_dict()
            
        except Exception as e:
            error_msg = f"Error fetching invitation: {str(e)}"
            self.logger.error(error_msg)
            return None

    def get_invitation_by_id(self, invitation_id: int, user_id: int) -> Optional[Dict]:
        """
        Get invitation by ID (with access control)
        
        Args:
            invitation_id: ID of the invitation
            user_id: ID of the requesting user
            
        Returns:
            Invitation dictionary or None if not found/access denied
        """
        try:
            invitation = Invitation.query.filter_by(
                id=invitation_id,
                is_deleted=False
            ).first()
            
            if not invitation:
                return None
            
            # Check access: inviter, invited user, or team admin
            has_access = (
                invitation.inviter_id == user_id or
                invitation.invited_user_id == user_id or
                self._verify_invitation_permission(invitation.team_id, user_id) is not None
            )
            
            if not has_access:
                return None
            
            return invitation.to_dict()
            
        except Exception as e:
            error_msg = f"Error fetching invitation: {str(e)}"
            self.logger.error(error_msg)
            return None

    def list_invitations(self, user_id: int, team_id: Optional[int] = None,
                        status: Optional[str] = None, page: int = 1,
                        per_page: int = 20) -> Dict:
        """
        List invitations for a user or team
        
        Args:
            user_id: ID of the requesting user
            team_id: Optional filter by team ID
            status: Optional filter by status
            page: Page number
            per_page: Items per page
            
        Returns:
            Dictionary with invitations list and pagination metadata
        """
        try:
            # Base query for invitations user has access to
            query = Invitation.query.filter(
                or_(
                    Invitation.inviter_id == user_id,  # Invitations sent by user
                    Invitation.invited_user_id == user_id,  # Invitations received by user
                    # Invitations for teams user can manage (owner/admin)
                    Invitation.team_id.in_(
                        db.session.query(Team.id).join(TeamMember).filter(
                            TeamMember.user_id == user_id,
                            TeamMember.is_deleted == False
                        ).filter(
                            or_(
                                Team.created_by == user_id,  # User owns team
                                TeamMember.role.in_(['owner', 'admin'])  # User is admin
                            )
                        )
                    )
                ),
                Invitation.is_deleted == False
            )
            
            # Filter by team if specified
            if team_id:
                # Relaxed access: allow if user is owner OR a member of the team (not only admins)
                team = Team.query.filter_by(id=team_id, is_deleted=False).first()
                if not team:
                    return {
                        'success': False,
                        'error': 'Team not found',
                        'invitations': [],
                        'pagination': {}
                    }
                is_owner = team.created_by == user_id
                is_member = TeamMember.query.filter_by(
                    team_id=team_id,
                    user_id=user_id,
                    is_deleted=False
                ).first() is not None
                if not (is_owner or is_member):
                    return {
                        'success': False,
                        'error': 'Access denied to team invitations',
                        'invitations': [],
                        'pagination': {}
                    }
                # When team_id is provided and user has at least membership, show ALL invitations for that team
                query = Invitation.query.filter(
                    Invitation.team_id == team_id,
                    Invitation.is_deleted == False
                )
            
            # Filter by status if specified
            if status:
                query = query.filter(Invitation.status == status)
            
            # Order by invited_at descending
            query = query.order_by(Invitation.invited_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            invitations = [invitation.to_summary_dict() for invitation in pagination.items]
            
            return {
                'success': True,
                'invitations': invitations,
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
            error_msg = f"Error listing invitations: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'invitations': [],
                'pagination': {}
            }

    def accept_invitation(self, token: str, user_id: int) -> InvitationResult:
        """
        Accept an invitation
        
        Args:
            token: Invitation token
            user_id: ID of the user accepting the invitation
            
        Returns:
            InvitationResult with success status
        """
        try:
            invitation = Invitation.get_by_token(token)
            
            if not invitation:
                return InvitationResult(
                    success=False,
                    error="Invitation not found"
                )
            
            if not invitation.can_be_accepted():
                return InvitationResult(
                    success=False,
                    error="Invitation cannot be accepted (expired or already processed)"
                )
            
            # Check if user email matches invitation email
            user = User.query.get(user_id)
            if not user or user.email.lower() != invitation.invited_email:
                return InvitationResult(
                    success=False,
                    error="Email mismatch - invitation was sent to a different email"
                )
            
            # Check if user is already a member
            if invitation.team.is_member(user_id):
                return InvitationResult(
                    success=False,
                    error="User is already a member of this team"
                )
            
            # Accept invitation
            invitation.accept(user_id)
            
            # Add user to team
            add_result = team_service.add_team_member(
                team_id=invitation.team_id,
                user_id=invitation.inviter_id,  # Use inviter as the one adding
                member_user_id=user_id,
                role=invitation.role
            )
            
            if not add_result.success:
                # Rollback invitation acceptance
                invitation.status = 'pending'
                invitation.responded_at = None
                invitation.accepted_at = None
                invitation.invited_user_id = None
                db.session.rollback()
                
                return InvitationResult(
                    success=False,
                    error=f"Failed to add user to team: {add_result.error}"
                )
            
            db.session.commit()
            
            # Send notification email to inviter
            self._send_invitation_accepted_notification(invitation)
            
            self.logger.info(f"Invitation accepted: {invitation.id} by user {user_id}")
            
            return InvitationResult(
                success=True,
                invitation=invitation.to_dict(),
                message="Invitation accepted successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error accepting invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)

    def decline_invitation(self, token: str, user_id: int) -> InvitationResult:
        """
        Decline an invitation
        
        Args:
            token: Invitation token
            user_id: ID of the user declining the invitation
            
        Returns:
            InvitationResult with success status
        """
        try:
            invitation = Invitation.get_by_token(token)
            
            if not invitation:
                return InvitationResult(
                    success=False,
                    error="Invitation not found"
                )
            
            if not invitation.can_be_declined():
                return InvitationResult(
                    success=False,
                    error="Invitation cannot be declined (expired or already processed)"
                )
            
            # Check if user email matches invitation email
            user = User.query.get(user_id)
            if not user or user.email.lower() != invitation.invited_email:
                return InvitationResult(
                    success=False,
                    error="Email mismatch - invitation was sent to a different email"
                )
            
            # Decline invitation
            invitation.decline(user_id)
            db.session.commit()
            
            # Send notification email to inviter
            self._send_invitation_declined_notification(invitation)
            
            self.logger.info(f"Invitation declined: {invitation.id} by user {user_id}")
            
            return InvitationResult(
                success=True,
                invitation=invitation.to_dict(),
                message="Invitation declined successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error declining invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)

    def cancel_invitation(self, invitation_id: int, user_id: int) -> InvitationResult:
        """
        Cancel an invitation
        
        Args:
            invitation_id: ID of the invitation
            user_id: ID of the user cancelling the invitation
            
        Returns:
            InvitationResult with success status
        """
        try:
            invitation = Invitation.query.filter_by(
                id=invitation_id,
                is_deleted=False
            ).first()
            
            if not invitation:
                return InvitationResult(
                    success=False,
                    error="Invitation not found"
                )
            
            # Verify user can cancel this invitation
            if not self._verify_invitation_permission(invitation.team_id, user_id):
                return InvitationResult(
                    success=False,
                    error="Access denied"
                )
            
            if not invitation.can_be_cancelled():
                return InvitationResult(
                    success=False,
                    error="Invitation cannot be cancelled (expired or already processed)"
                )
            
            # Cancel invitation
            invitation.cancel(user_id)
            db.session.commit()
            
            self.logger.info(f"Invitation cancelled: {invitation.id} by user {user_id}")
            
            return InvitationResult(
                success=True,
                invitation=invitation.to_dict(),
                message="Invitation cancelled successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error cancelling invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)

    def delete_invitation(self, invitation_id: int = None, invited_email: str = None, user_id: int = None) -> InvitationResult:
        """
        Hard delete an invitation by id or invited_email (most recent match)
        
        Args:
            invitation_id: ID of the invitation (optional)
            invited_email: Invited email to match (optional)
            user_id: ID of the user deleting the invitation
            
        Returns:
            InvitationResult with success status
        """
        try:
            if not invitation_id and not invited_email:
                return InvitationResult(success=False, error="Either invitation_id or invited_email is required")

            invitation = None
            if invitation_id:
                invitation = Invitation.query.filter_by(id=invitation_id).first()
            elif invited_email:
                invitation = (
                    Invitation.query.filter_by(invited_email=invited_email.lower().strip())
                    .order_by(Invitation.invited_at.desc())
                    .first()
                )
            
            if not invitation:
                return InvitationResult(success=False, error="Invitation not found")
            
            # Verify user can delete this invitation (same permissions as cancel)
            if not self._verify_invitation_permission(invitation.team_id, user_id):
                return InvitationResult(success=False, error="Access denied")
            
            # Perform hard delete
            db.session.delete(invitation)
            db.session.commit()
            
            self.logger.info(f"Invitation deleted (hard): {getattr(invitation, 'id', invitation_id)} by user {user_id}")
            
            return InvitationResult(success=True, invitation=None, message="Invitation deleted successfully")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)
    def resend_invitation(self, invitation_id: int, user_id: int) -> InvitationResult:
        """
        Resend an invitation (create new invitation for same email/team)
        
        Args:
            invitation_id: ID of the original invitation
            user_id: ID of the user resending the invitation
            
        Returns:
            InvitationResult with success status
        """
        try:
            original_invitation = Invitation.query.filter_by(
                id=invitation_id,
                is_deleted=False
            ).first()
            
            if not original_invitation:
                return InvitationResult(
                    success=False,
                    error="Original invitation not found"
                )
            
            # Verify user can resend this invitation
            if not self._verify_invitation_permission(original_invitation.team_id, user_id):
                return InvitationResult(
                    success=False,
                    error="Access denied"
                )
            
            # Cancel original invitation
            original_invitation.cancel(user_id)
            
            # Create new invitation
            new_invitation = Invitation.create_invitation(
                team_id=original_invitation.team_id,
                inviter_id=user_id,
                invited_email=original_invitation.invited_email,
                role=original_invitation.role,
                message=original_invitation.message
            )
            
            db.session.add(new_invitation)
            db.session.commit()
            
            self.logger.info(f"Invitation resent: {new_invitation.id} by user {user_id}")
            
            return InvitationResult(
                success=True,
                invitation=new_invitation.to_dict(),
                message="Invitation resent successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error resending invitation: {str(e)}"
            self.logger.error(error_msg)
            return InvitationResult(success=False, error=error_msg)

    def cleanup_expired_invitations(self) -> int:
        """
        Mark expired invitations as expired
        
        Returns:
            Number of invitations marked as expired
        """
        try:
            expired_count = Invitation.cleanup_expired()
            db.session.commit()
            
            self.logger.info(f"Marked {expired_count} invitations as expired")
            
            return expired_count
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error cleaning up expired invitations: {str(e)}"
            self.logger.error(error_msg)
            return 0

    def get_invitation_statistics(self, user_id: int) -> Dict:
        """
        Get invitation statistics for a user
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with invitation statistics
        """
        try:
            # Invitations sent by user
            sent_invitations = Invitation.query.filter_by(
                inviter_id=user_id,
                is_deleted=False
            ).count()
            
            # Invitations received by user
            received_invitations = Invitation.query.filter_by(
                invited_user_id=user_id,
                is_deleted=False
            ).count()
            
            # Pending invitations sent
            pending_sent = Invitation.query.filter_by(
                inviter_id=user_id,
                status='pending',
                is_deleted=False
            ).filter(Invitation.expires_at > datetime.now(UTC)).count()
            
            # Pending invitations received
            pending_received = Invitation.query.filter_by(
                invited_user_id=user_id,
                status='pending',
                is_deleted=False
            ).filter(Invitation.expires_at > datetime.now(UTC)).count()
            
            return {
                'sent_invitations': sent_invitations,
                'received_invitations': received_invitations,
                'pending_sent': pending_sent,
                'pending_received': pending_received,
                'total_invitations': sent_invitations + received_invitations
            }
            
        except Exception as e:
            error_msg = f"Error getting invitation statistics: {str(e)}"
            self.logger.error(error_msg)
            return {
                'sent_invitations': 0,
                'received_invitations': 0,
                'pending_sent': 0,
                'pending_received': 0,
                'total_invitations': 0,
                'error': error_msg
            }

    def health_check(self) -> Dict:
        """
        Health check for invitation service
        
        Returns:
            Dictionary with health status
        """
        try:
            # Test database connectivity
            invitation_count = Invitation.query.count()
            pending_count = Invitation.query.filter_by(
                status='pending',
                is_deleted=False
            ).count()
            
            return {
                'status': 'healthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'total_invitations_in_system': invitation_count,
                'pending_invitations': pending_count
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'error': str(e)
            }

    def _send_invitation_email(self, invitation: Invitation, team: Team):
        """Send invitation email to the invited user"""
        try:
            # Get inviter information
            inviter = User.query.get(invitation.inviter_id)
            inviter_name = f"{inviter.first_name} {inviter.last_name}" if inviter else "Unknown User"
            
            # Create an invitation link (you'll need to configure your frontend URL)
            frontend_url = os.getenv('FRONTEND_URL', 'https://polaris-dev.netlify.app')
            invitation_link = f"{frontend_url}/invitation/setup-account/{invitation.token}"

            # Calculate days until expiry
            days_until_expiry = invitation.days_until_expiry()
            
            # Send email
            email_result = email_service.send_team_invitation_email(
                invited_email=invitation.invited_email,
                team_name=team.name,
                inviter_name=inviter_name,
                invitation_link=invitation_link,
                role=invitation.role,
                message=invitation.message,
                expires_in_days=days_until_expiry
            )
            
            if email_result['success']:
                self.logger.info(f"Invitation email sent to {invitation.invited_email}")
            else:
                self.logger.error(f"Failed to send invitation email: {email_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.logger.error(f"Error sending invitation email: {str(e)}")

    def _send_invitation_accepted_notification(self, invitation: Invitation):
        """Send notification email to inviter when invitation is accepted"""
        try:
            # Get inviter information
            inviter = User.query.get(invitation.inviter_id)
            if not inviter:
                return
                
            # Get invited user information
            invited_user = User.query.get(invitation.invited_user_id)
            invited_user_name = f"{invited_user.first_name} {invited_user.last_name}" if invited_user else "Unknown User"
            
            # Get team information
            team = Team.query.get(invitation.team_id)
            team_name = team.name if team else "Unknown Team"
            
            # Send notification email
            email_result = email_service.send_invitation_accepted_notification(
                inviter_email=inviter.email,
                invited_user_name=invited_user_name,
                team_name=team_name
            )
            
            if email_result['success']:
                self.logger.info(f"Invitation accepted notification sent to {inviter.email}")
            else:
                self.logger.error(f"Failed to send acceptance notification: {email_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.logger.error(f"Error sending invitation accepted notification: {str(e)}")

    def _send_invitation_declined_notification(self, invitation: Invitation):
        """Send notification email to inviter when invitation is declined"""
        try:
            # Get inviter information
            inviter = User.query.get(invitation.inviter_id)
            if not inviter:
                return
                
            # Get invited user information
            invited_user = User.query.get(invitation.invited_user_id)
            invited_user_name = f"{invited_user.first_name} {invited_user.last_name}" if invited_user else "Unknown User"
            
            # Get team information
            team = Team.query.get(invitation.team_id)
            team_name = team.name if team else "Unknown Team"
            
            # Send notification email
            email_result = email_service.send_invitation_declined_notification(
                inviter_email=inviter.email,
                invited_user_name=invited_user_name,
                team_name=team_name
            )
            
            if email_result['success']:
                self.logger.info(f"Invitation declined notification sent to {inviter.email}")
            else:
                self.logger.error(f"Failed to send decline notification: {email_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.logger.error(f"Error sending invitation declined notification: {str(e)}")


# Global instance
invitation_service = InvitationService()
