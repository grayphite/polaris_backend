"""
Chat Reference model for POLARIS system

Stores AI-generated summaries of referenced chats for reuse across multiple conversations.
"""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.extensions import db


class ChatReference(db.Model):
    """
    Model for storing AI-generated summaries of referenced chats
    
    One summary per referenced chat (unique constraint on referenced_chat_id),
    reusable across all chats that reference it.
    """
    __tablename__ = 'chat_references'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to referenced chat (unique - one summary per chat)
    referenced_chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    
    # Summary content
    summary = db.Column(db.Text, nullable=False)
    
    # Summary metadata
    summary_model = db.Column(db.String(100), nullable=True)  # e.g., "claude-3-haiku-20240307"
    summary_tokens = db.Column(db.Integer, nullable=True)  # Tokens used for summary generation
    referenced_chat_message_count = db.Column(db.Integer, nullable=True)  # Number of messages summarized
    last_message_id_included = db.Column(db.Integer, nullable=True)  # Last AIChat.id included (for refresh detection)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # User tracking
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_refreshed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    referenced_chat = db.relationship('Chat', foreign_keys=[referenced_chat_id], backref='chat_reference')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_chat_references')
    refresher = db.relationship('User', foreign_keys=[last_refreshed_by], backref='refreshed_chat_references')
    
    def __repr__(self):
        return f'<ChatReference {self.id}: Chat {self.referenced_chat_id}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ChatReference to dictionary representation"""
        return {
            'id': self.id,
            'referenced_chat_id': self.referenced_chat_id,
            'summary': self.summary,
            'summary_model': self.summary_model,
            'summary_tokens': self.summary_tokens,
            'referenced_chat_message_count': self.referenced_chat_message_count,
            'last_message_id_included': self.last_message_id_included,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'created_by': self.created_by,
            'last_refreshed_by': self.last_refreshed_by,
            'referenced_chat': self.referenced_chat.to_dict() if self.referenced_chat else None
        }

