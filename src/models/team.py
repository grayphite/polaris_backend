"""
Team model for POLARIS system
"""
from datetime import datetime, UTC
from src.extensions import db


class Team(db.Model):
    """Model for teams in POLARIS system"""
    __tablename__ = 'teams'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Core fields
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), 
                          onupdate=lambda: datetime.now(UTC))
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    # User tracking
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Soft delete flag
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_teams')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_teams')
    members = db.relationship('TeamMember', back_populates='team', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Team {self.id}: {self.name}>'
    
    def to_dict(self):
        """Convert team to dictionary representation"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'created_by': self.created_by,
            'deleted_by': self.deleted_by,
            'is_deleted': self.is_deleted,
            'member_count': len([member for member in self.members if not member.is_deleted])
        }
    
    def to_summary_dict(self):
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
            'is_deleted': self.is_deleted,
            'member_count': len([member for member in self.members if not member.is_deleted])
        }
    
    def get_members(self):
        """Get all active team members"""
        return [member for member in self.members if not member.is_deleted]
    
    def get_member_by_user_id(self, user_id: int):
        """Get team member by user ID"""
        for member in self.members:
            if member.user_id == user_id and not member.is_deleted:
                return member
        return None
    
    def is_member(self, user_id: int) -> bool:
        """Check if user is a member of this team"""
        return self.get_member_by_user_id(user_id) is not None
    
    def is_owner(self, user_id: int) -> bool:
        """Check if user is the owner of this team"""
        return self.created_by == user_id


class TeamMember(db.Model):
    """Model for team memberships"""
    __tablename__ = 'team_members'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Member role and permissions
    role = db.Column(db.String(50), nullable=False, default='member')  # owner, admin, member
    permissions = db.Column(db.JSON, nullable=True)  # Additional permissions as JSON
    
    # Timestamps
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), 
                          onupdate=lambda: datetime.now(UTC))
    left_at = db.Column(db.DateTime, nullable=True)
    
    # User tracking
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who added this member
    removed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who removed this member
    
    # Soft delete flag
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Relationships
    team = db.relationship('Team', back_populates='members')
    user = db.relationship('User', foreign_keys=[user_id], backref='team_memberships')
    adder = db.relationship('User', foreign_keys=[added_by], backref='added_team_members')
    remover = db.relationship('User', foreign_keys=[removed_by], backref='removed_team_members')
    
    # Unique constraint to prevent duplicate memberships
    __table_args__ = (db.UniqueConstraint('team_id', 'user_id', name='unique_team_member'),)
    
    def __repr__(self):
        return f'<TeamMember {self.id}: User {self.user_id} in Team {self.team_id}>'
    
    def to_dict(self):
        """Convert team member to dictionary representation"""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'user_id': self.user_id,
            'role': self.role,
            'permissions': self.permissions,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'left_at': self.left_at.isoformat() if self.left_at else None,
            'added_by': self.added_by,
            'removed_by': self.removed_by,
            'is_deleted': self.is_deleted
        }
    
    def to_summary_dict(self):
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'user_id': self.user_id,
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'is_deleted': self.is_deleted
        }
    
    def has_permission(self, permission: str) -> bool:
        """Check if member has specific permission"""
        if not self.permissions:
            return False
        return permission in self.permissions
    
    def can_manage_team(self) -> bool:
        """Check if member can manage team (owner or admin)"""
        return self.role in ['owner', 'admin']
    
    def can_add_members(self) -> bool:
        """Check if member can add other members"""
        return self.role in ['owner', 'admin'] or self.has_permission('add_members')
    
    def can_remove_members(self) -> bool:
        """Check if member can remove other members"""
        return self.role in ['owner', 'admin'] or self.has_permission('remove_members')



