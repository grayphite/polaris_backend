"""
Invitation model for POLARIS system

Handles team invitations with expiration, status tracking,
and comprehensive audit trail.
"""
from datetime import datetime, UTC, timedelta
from src.extensions import db


class Invitation(db.Model):
    """Model for team invitations"""
    __tablename__ = 'invitations'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Core invitation fields
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True)
    inviter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    invited_email = db.Column(db.String(255), nullable=False, index=True)
    invited_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # Set when user exists
    
    # Invitation details
    role = db.Column(db.String(50), nullable=False, default='member')  # Role to be assigned
    message = db.Column(db.Text, nullable=True)  # Optional invitation message
    
    # Status and lifecycle
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending, accepted, declined, expired, cancelled
    token = db.Column(db.String(255), nullable=False, unique=True, index=True)  # Unique invitation token
    
    # Timestamps
    invited_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    responded_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    declined_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    
    # User tracking
    cancelled_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who cancelled the invitation
    
    # Soft delete flag
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    team = db.relationship('Team', backref='invitations')
    inviter = db.relationship('User', foreign_keys=[inviter_id], backref='sent_invitations')
    invited_user = db.relationship('User', foreign_keys=[invited_user_id], backref='received_invitations')
    canceller = db.relationship('User', foreign_keys=[cancelled_by], backref='cancelled_invitations')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_invitations')
    
    # Unique constraint to prevent duplicate invitations
    __table_args__ = (
        db.UniqueConstraint('team_id', 'invited_email', 'status', name='unique_active_invitation'),
        db.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'expired', 'cancelled')", name='valid_status'),
    )
    
    def __repr__(self):
        return f'<Invitation {self.id}: {self.invited_email} -> Team {self.team_id}>'
    
    def to_dict(self):
        """Convert invitation to dictionary representation"""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'inviter_id': self.inviter_id,
            'invited_email': self.invited_email,
            'invited_user_id': self.invited_user_id,
            'role': self.role,
            'message': self.message,
            'status': self.status,
            'token': self.token,
            'invited_at': self.invited_at.isoformat() if self.invited_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'responded_at': self.responded_at.isoformat() if self.responded_at else None,
            'accepted_at': self.accepted_at.isoformat() if self.accepted_at else None,
            'declined_at': self.declined_at.isoformat() if self.declined_at else None,
            'cancelled_at': self.cancelled_at.isoformat() if self.cancelled_at else None,
            'cancelled_by': self.cancelled_by,
            'is_deleted': self.is_deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'deleted_by': self.deleted_by,
            'is_expired': self.is_expired(),
            'days_until_expiry': self.days_until_expiry()
        }
    
    def to_summary_dict(self):
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'invited_email': self.invited_email,
            'role': self.role,
            'status': self.status,
            'invited_at': self.invited_at.isoformat() if self.invited_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_expired': self.is_expired(),
            'days_until_expiry': self.days_until_expiry()
        }
    
    def is_expired(self) -> bool:
        """Check if invitation is expired"""
        if self.status in ['accepted', 'declined', 'cancelled']:
            return False
        # Convert expires_at to UTC if it's naive
        expires_at_utc = self.expires_at
        if expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=UTC)
        return datetime.now(UTC) > expires_at_utc
    
    def is_valid(self) -> bool:
        """Check if invitation is valid (not expired and pending)"""
        return self.status == 'pending' and not self.is_expired()
    
    def days_until_expiry(self) -> int:
        """Get days until invitation expires"""
        if self.is_expired():
            return 0
        # Convert expires_at to UTC if it's naive
        expires_at_utc = self.expires_at
        if expires_at_utc.tzinfo is None:
            expires_at_utc = expires_at_utc.replace(tzinfo=UTC)
        delta = expires_at_utc - datetime.now(UTC)
        return max(0, delta.days)
    
    def can_be_cancelled(self) -> bool:
        """Check if invitation can be cancelled"""
        return self.status == 'pending' and not self.is_expired()
    
    def can_be_accepted(self) -> bool:
        """Check if invitation can be accepted"""
        return self.is_valid()
    
    def can_be_declined(self) -> bool:
        """Check if invitation can be declined"""
        return self.is_valid()
    
    def accept(self, user_id: int = None):
        """Accept the invitation"""
        if not self.can_be_accepted():
            raise ValueError("Invitation cannot be accepted")
        
        self.status = 'accepted'
        self.responded_at = datetime.now(UTC)
        self.accepted_at = datetime.now(UTC)
        if user_id:
            self.invited_user_id = user_id
    
    def decline(self, user_id: int = None):
        """Decline the invitation"""
        if not self.can_be_declined():
            raise ValueError("Invitation cannot be declined")
        
        self.status = 'declined'
        self.responded_at = datetime.now(UTC)
        self.declined_at = datetime.now(UTC)
        if user_id:
            self.invited_user_id = user_id
    
    def cancel(self, cancelled_by: int):
        """Cancel the invitation"""
        if not self.can_be_cancelled():
            raise ValueError("Invitation cannot be cancelled")
        
        self.status = 'cancelled'
        self.cancelled_at = datetime.now(UTC)
        self.cancelled_by = cancelled_by
    
    def expire(self):
        """Mark invitation as expired"""
        if self.status == 'pending':
            self.status = 'expired'
    
    @classmethod
    def create_invitation(cls, team_id: int, inviter_id: int, invited_email: str,
                         role: str = 'member', message: str = None,
                         expires_in_days: int = 7) -> 'Invitation':
        """
        Create a new invitation with auto-generated token and expiration
        
        Args:
            team_id: ID of the team
            inviter_id: ID of the user sending the invitation
            invited_email: Email of the invited user
            role: Role to assign to the invited user
            message: Optional invitation message
            expires_in_days: Days until invitation expires (default: 7)
            
        Returns:
            Invitation object
        """
        import secrets
        
        # Generate unique token
        token = secrets.token_urlsafe(32)
        
        # Calculate expiration date
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
        
        invitation = cls(
            team_id=team_id,
            inviter_id=inviter_id,
            invited_email=invited_email.lower().strip(),
            role=role,
            message=message,
            token=token,
            expires_at=expires_at,
            status='pending'
        )
        
        return invitation
    
    @classmethod
    def get_by_token(cls, token: str) -> 'Invitation':
        """Get invitation by token"""
        return cls.query.filter_by(token=token, is_deleted=False).first()
    
    @classmethod
    def get_pending_for_email(cls, email: str) -> list:
        """Get all pending invitations for an email"""
        return cls.query.filter_by(
            invited_email=email.lower().strip(),
            status='pending',
            is_deleted=False
        ).filter(cls.expires_at > datetime.now(UTC)).all()
    
    @classmethod
    def get_pending_for_team(cls, team_id: int) -> list:
        """Get all pending invitations for a team"""
        return cls.query.filter_by(
            team_id=team_id,
            status='pending',
            is_deleted=False
        ).filter(cls.expires_at > datetime.now(UTC)).all()
    
    @classmethod
    def cleanup_expired(cls):
        """Mark expired invitations as expired"""
        expired_count = cls.query.filter_by(
            status='pending',
            is_deleted=False
        ).filter(cls.expires_at <= datetime.now(UTC)).update({
            'status': 'expired'
        })
        return expired_count
