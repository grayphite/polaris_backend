"""
Chat model for POLARIS system
"""
from datetime import datetime, UTC
from src.extensions import db


class Chat(db.Model):
    """Model for chats associated with projects"""
    __tablename__ = 'chats'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Core fields
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Parent relationship
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    
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
    project = db.relationship('Project', back_populates='chats')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_chats')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_chats')
    
    def __repr__(self):
        return f'<Chat {self.id}: {self.name}>'
    
    def to_dict(self):
        """Convert chat to dictionary representation"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'project_id': self.project_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'created_by': self.created_by,
            'deleted_by': self.deleted_by,
            'is_deleted': self.is_deleted
        }
    
    def to_summary_dict(self):
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'project_id': self.project_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'is_deleted': self.is_deleted
        }


