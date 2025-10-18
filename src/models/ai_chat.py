"""
AI Chat models for POLARIS system

Models for storing AI chat conversations and statistics.
Supports multiple AI providers (OpenAI, Claude, Google, etc.)
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.extensions import db


class AIChat(db.Model):
    """
    Model for AI chat conversations
    
    This is a child table of Chat model, storing individual AI conversations
    with support for multiple AI providers and models.
    """
    __tablename__ = 'ai_chats'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    chat_id = db.Column(db.Integer, db.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Chat content
    user_question = db.Column(db.Text, nullable=False)
    ai_answer = db.Column(db.Text, nullable=False)
    chat_name = db.Column(db.String(100), nullable=True)  # AI-generated name/label for this chat
    
    # AI model information
    ai_model = db.Column(db.String(100), nullable=False)  # e.g., "gpt-4", "claude-3-haiku"
    ai_model_provider = db.Column(db.String(50), nullable=False)  # e.g., "OpenAI", "Claude", "Google"
    
    # Context and metadata
    context_metadata = db.Column(db.JSON, nullable=True)  # Additional AI response info
    conversation_context = db.Column(db.Text, nullable=True)  # Previous conversation context
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    chat = db.relationship('Chat', back_populates='ai_conversations')
    user = db.relationship('User', foreign_keys=[user_id], backref='ai_chats')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_ai_chats')
    ai_stats = db.relationship('AIStats', back_populates='ai_chat', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AIChat {self.id}: {self.ai_model_provider}-{self.ai_model}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert AIChat to dictionary representation"""
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'user_id': self.user_id,
            'user_question': self.user_question,
            'ai_answer': self.ai_answer,
            'chat_name': self.chat_name,
            'ai_model': self.ai_model,
            'ai_model_provider': self.ai_model_provider,
            'context_metadata': self.context_metadata,
            'conversation_context': self.conversation_context,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_deleted': self.is_deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
            'deleted_by': self.deleted_by
        }
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'user_question': self.user_question[:100] + '...' if len(self.user_question) > 100 else self.user_question,
            'chat_name': self.chat_name,
            'ai_model': self.ai_model,
            'ai_model_provider': self.ai_model_provider,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_deleted': self.is_deleted
        }


class AIStats(db.Model):
    """
    Model for AI chat statistics and audit information
    
    Stores usage statistics, performance metrics, and audit data
    for each AI chat conversation.
    """
    __tablename__ = 'ai_stats'

    # Primary key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to AIChat
    ai_chat_id = db.Column(db.Integer, db.ForeignKey('ai_chats.id'), nullable=False, unique=True, index=True)
    
    # Usage statistics
    tokens_used = db.Column(db.Integer, nullable=True)  # Total tokens consumed
    prompt_tokens = db.Column(db.Integer, nullable=True)  # Input tokens
    completion_tokens = db.Column(db.Integer, nullable=True)  # Output tokens
    
    # Performance metrics
    response_time_ms = db.Column(db.Integer, nullable=True)  # Response time in milliseconds
    cost_usd = db.Column(db.Numeric(10, 6), nullable=True)  # Cost in USD
    
    # Quality metrics
    user_rating = db.Column(db.Integer, nullable=True)  # User rating 1-5
    feedback = db.Column(db.Text, nullable=True)  # User feedback
    
    # Technical metadata
    api_version = db.Column(db.String(20), nullable=True)  # API version used
    request_id = db.Column(db.String(100), nullable=True)  # Provider request ID
    error_occurred = db.Column(db.Boolean, default=False, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    
    # Audit information
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    ai_chat = db.relationship('AIChat', back_populates='ai_stats')
    
    def __repr__(self):
        return f'<AIStats {self.id}: Chat {self.ai_chat_id}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert AIStats to dictionary representation"""
        return {
            'id': self.id,
            'ai_chat_id': self.ai_chat_id,
            'tokens_used': self.tokens_used,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'response_time_ms': self.response_time_ms,
            'cost_usd': float(self.cost_usd) if self.cost_usd else None,
            'user_rating': self.user_rating,
            'feedback': self.feedback,
            'api_version': self.api_version,
            'request_id': self.request_id,
            'error_occurred': self.error_occurred,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to summary dictionary for list views"""
        return {
            'id': self.id,
            'ai_chat_id': self.ai_chat_id,
            'tokens_used': self.tokens_used,
            'response_time_ms': self.response_time_ms,
            'cost_usd': float(self.cost_usd) if self.cost_usd else None,
            'user_rating': self.user_rating,
            'error_occurred': self.error_occurred,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
