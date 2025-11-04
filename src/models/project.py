"""
Project model for POLARIS system
"""
from datetime import datetime, UTC
from src.extensions import db


class Project(db.Model):
    """Model for user projects in POLARIS system"""
    __tablename__ = 'projects'

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
    
    # Public/Private flag
    is_public = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_projects')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_projects')
    chats = db.relationship('Chat', back_populates='project', lazy='dynamic', cascade='all, delete-orphan')
    members = db.relationship('ProjectMember', back_populates='project', cascade='all, delete-orphan', lazy='dynamic')
    
    def __repr__(self):
        return f'<Project {self.id}: {self.name}>'
    
    def to_dict(self):
        """Convert project to dictionary representation"""
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
            'is_public': self.is_public
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
            'is_public': self.is_public,
            'chat_count': len([chat for chat in self.chats if not chat.is_deleted])
        }

    def get_member_by_user_id(self, user_id: int):
        for member in self.members:
            if member.user_id == user_id and not member.is_deleted:
                return member
        return None

    def is_member(self, user_id: int) -> bool:
        return self.get_member_by_user_id(user_id) is not None


class ProjectMember(db.Model):
    """Model for project memberships"""
    __tablename__ = 'project_members'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
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
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    removed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Soft delete flag
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Relationships
    project = db.relationship('Project', back_populates='members')
    user = db.relationship('User', foreign_keys=[user_id], backref='project_memberships')
    adder = db.relationship('User', foreign_keys=[added_by], backref='added_project_members')
    remover = db.relationship('User', foreign_keys=[removed_by], backref='removed_project_members')

    # Unique constraint to prevent duplicate memberships
    __table_args__ = (db.UniqueConstraint('project_id', 'user_id', name='unique_project_member'),)

    def __repr__(self):
        return f'<ProjectMember {self.id}: User {self.user_id} in Project {self.project_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
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
        return {
            'id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'is_deleted': self.is_deleted
        }

    def has_permission(self, permission: str) -> bool:
        if not self.permissions:
            return False
        return permission in self.permissions

    def can_manage_project(self) -> bool:
        return self.role in ['owner', 'admin']

