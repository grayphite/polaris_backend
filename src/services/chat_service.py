"""
ChatService - Business logic for chat management

Handles CRUD operations for chats with parent project relationship
and automatic project touch (update parent project's updated_at).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Optional, List

from sqlalchemy import or_, and_
from src.extensions import db
from src.models.chat import Chat
from src.models.project import Project


logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """Result of a chat operation"""
    success: bool
    chat: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ChatService:
    """Service for managing chats with full CRUD operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def _touch_project(self, project_id: int):
        """
        Touch parent project to update its updated_at timestamp
        
        Args:
            project_id: ID of the project to touch
        """
        try:
            project = Project.query.get(project_id)
            if project:
                project.updated_at = datetime.now(UTC)
        except Exception as e:
            self.logger.warning(f"Failed to touch project {project_id}: {str(e)}")

    def _verify_project_access(self, project_id: int, user_id: int) -> bool:
        """
        Verify user has access to the project (either owns it or it's public)
        
        Args:
            project_id: ID of the project
            user_id: ID of the user
            
        Returns:
            True if user has access, False otherwise
        """
        project = Project.query.filter_by(
            id=project_id,
            is_deleted=False
        ).first()
        
        if not project:
            return False
        
        # Allow access if user owns the project OR if project is public
        return project.created_by == user_id or project.is_public

    def create_chat(self, name: str, project_id: int, user_id: int,
                   description: Optional[str] = None) -> ChatResult:
        """
        Create a new chat
        
        Args:
            name: Name of the chat
            project_id: ID of the parent project
            user_id: ID of the user creating the chat
            description: Optional chat description
            
        Returns:
            ChatResult with success status and chat data
        """
        try:
            # Validate input
            if not name or not name.strip():
                return ChatResult(
                    success=False,
                    error="Chat name is required"
                )
            
            if len(name) > 255:
                return ChatResult(
                    success=False,
                    error="Chat name must be less than 255 characters"
                )
            
            # Verify project exists and user owns it
            if not self._verify_project_access(project_id, user_id):
                return ChatResult(
                    success=False,
                    error="Project not found or access denied"
                )
            
            # Create chat
            chat = Chat(
                name=name.strip(),
                description=description,
                project_id=project_id,
                created_by=user_id,
                is_deleted=False
            )
            
            db.session.add(chat)
            
            # Touch parent project
            self._touch_project(project_id)
            
            db.session.commit()
            
            self.logger.info(f"Chat created: {chat.id} in project {project_id} by user {user_id}")
            
            return ChatResult(
                success=True,
                chat=chat.to_dict(),
                message="Chat created successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating chat: {str(e)}"
            self.logger.error(error_msg)
            return ChatResult(success=False, error=error_msg)

    def get_chat_by_id(self, chat_id: int, user_id: int,
                      include_deleted: bool = False) -> Optional[Dict]:
        """
        Get a specific chat by ID
        
        Args:
            chat_id: ID of the chat
            user_id: ID of the requesting user
            include_deleted: Whether to include soft-deleted chats
            
        Returns:
            Chat dictionary or None if not found
        """
        try:
            query = Chat.query.filter_by(id=chat_id)
            
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            
            chat = query.first()
            
            if not chat:
                return None
            
            # Verify user owns the parent project
            if not self._verify_project_access(chat.project_id, user_id):
                return None
            
            return chat.to_dict()
            
        except Exception as e:
            error_msg = f"Error fetching chat: {str(e)}"
            self.logger.error(error_msg)
            return None

    def list_chats(self, user_id: int, project_id: Optional[int] = None,
                  page: int = 1, per_page: int = 20,
                  search: str = None, include_deleted: bool = False) -> Dict:
        """
        List chats with pagination and search
        
        Args:
            user_id: ID of the requesting user
            project_id: Optional filter by project ID
            page: Page number (1-indexed)
            per_page: Items per page
            search: Optional search query
            include_deleted: Whether to include soft-deleted chats
            
        Returns:
            Dictionary with chats list and pagination metadata
        """
        try:
            # Start with chats from user's projects OR public projects
            query = Chat.query.join(Project).filter(
                or_(
                    Project.created_by == user_id,  # User's own projects
                    Project.is_public == True        # Public projects
                )
            )
            
            # Filter by project if specified
            if project_id:
                # Verify user owns the project
                if not self._verify_project_access(project_id, user_id):
                    return {
                        'success': False,
                        'error': 'Project not found or access denied',
                        'chats': [],
                        'pagination': {}
                    }
                query = query.filter(Chat.project_id == project_id)
            
            # Filter deleted chats
            if not include_deleted:
                query = query.filter(Chat.is_deleted == False)
            
            # Search functionality
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        Chat.name.ilike(search_term),
                        Chat.description.ilike(search_term)
                    )
                )
            
            # Order by created_at descending
            query = query.order_by(Chat.created_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            chats = [chat.to_summary_dict() for chat in pagination.items]
            
            return {
                'success': True,
                'chats': chats,
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
            error_msg = f"Error listing chats: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'chats': [],
                'pagination': {}
            }

    def list_chats_by_project(self, project_id: int, user_id: int,
                             page: int = 1, per_page: int = 20,
                             search: str = None) -> Dict:
        """
        List all chats for a specific project
        
        Args:
            project_id: ID of the project
            user_id: ID of the requesting user
            page: Page number
            per_page: Items per page
            search: Optional search query
            
        Returns:
            Dictionary with chats list and pagination metadata
        """
        return self.list_chats(
            user_id=user_id,
            project_id=project_id,
            page=page,
            per_page=per_page,
            search=search,
            include_deleted=False
        )

    def update_chat(self, chat_id: int, user_id: int,
                   data: Dict) -> ChatResult:
        """
        Update an existing chat
        
        Args:
            chat_id: ID of the chat to update
            user_id: ID of the requesting user
            data: Dictionary with fields to update
            
        Returns:
            ChatResult with updated chat data
        """
        try:
            chat = Chat.query.filter_by(
                id=chat_id,
                is_deleted=False
            ).first()
            
            if not chat:
                return ChatResult(
                    success=False,
                    error="Chat not found"
                )
            
            # Verify user owns the parent project
            if not self._verify_project_access(chat.project_id, user_id):
                return ChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Update allowed fields
            if 'name' in data:
                if not data['name'] or not data['name'].strip():
                    return ChatResult(
                        success=False,
                        error="Chat name cannot be empty"
                    )
                chat.name = data['name'].strip()
            
            if 'description' in data:
                chat.description = data.get('description')
            
            chat.updated_at = datetime.now(UTC)
            
            # Touch parent project
            self._touch_project(chat.project_id)
            
            db.session.commit()
            
            self.logger.info(f"Chat updated: {chat.id} by user {user_id}")
            
            return ChatResult(
                success=True,
                chat=chat.to_dict(),
                message="Chat updated successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating chat: {str(e)}"
            self.logger.error(error_msg)
            return ChatResult(success=False, error=error_msg)

    def delete_chat(self, chat_id: int, user_id: int) -> ChatResult:
        """
        Soft delete a chat
        
        Args:
            chat_id: ID of the chat to delete
            user_id: ID of the user deleting the chat
            
        Returns:
            ChatResult indicating success or failure
        """
        try:
            chat = Chat.query.filter_by(
                id=chat_id,
                is_deleted=False
            ).first()
            
            if not chat:
                return ChatResult(
                    success=False,
                    error="Chat not found or already deleted"
                )
            
            # Verify user owns the parent project
            if not self._verify_project_access(chat.project_id, user_id):
                return ChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Soft delete
            chat.is_deleted = True
            chat.deleted_at = datetime.now(UTC)
            chat.deleted_by = user_id
            chat.updated_at = datetime.now(UTC)
            
            # Touch parent project
            self._touch_project(chat.project_id)
            
            db.session.commit()
            
            self.logger.info(f"Chat soft-deleted: {chat.id} by user {user_id}")
            
            return ChatResult(
                success=True,
                message="Chat deleted successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting chat: {str(e)}"
            self.logger.error(error_msg)
            return ChatResult(success=False, error=error_msg)

    def restore_chat(self, chat_id: int, user_id: int) -> ChatResult:
        """
        Restore a soft-deleted chat
        
        Args:
            chat_id: ID of the chat to restore
            user_id: ID of the requesting user
            
        Returns:
            ChatResult with restored chat data
        """
        try:
            chat = Chat.query.filter_by(
                id=chat_id,
                is_deleted=True
            ).first()
            
            if not chat:
                return ChatResult(
                    success=False,
                    error="Chat not found or not deleted"
                )
            
            # Verify user owns the parent project
            if not self._verify_project_access(chat.project_id, user_id):
                return ChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Restore chat
            chat.is_deleted = False
            chat.deleted_at = None
            chat.deleted_by = None
            chat.updated_at = datetime.now(UTC)
            
            # Touch parent project
            self._touch_project(chat.project_id)
            
            db.session.commit()
            
            self.logger.info(f"Chat restored: {chat.id} by user {user_id}")
            
            return ChatResult(
                success=True,
                chat=chat.to_dict(),
                message="Chat restored successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error restoring chat: {str(e)}"
            self.logger.error(error_msg)
            return ChatResult(success=False, error=error_msg)

    def permanent_delete_chat(self, chat_id: int, user_id: int) -> ChatResult:
        """
        Permanently delete a chat (use with caution)
        
        Args:
            chat_id: ID of the chat to permanently delete
            user_id: ID of the requesting user
            
        Returns:
            ChatResult indicating success or failure
        """
        try:
            chat = Chat.query.filter_by(id=chat_id).first()
            
            if not chat:
                return ChatResult(
                    success=False,
                    error="Chat not found"
                )
            
            # Verify user owns the parent project
            if not self._verify_project_access(chat.project_id, user_id):
                return ChatResult(
                    success=False,
                    error="Access denied"
                )
            
            project_id = chat.project_id
            
            # Permanent deletion
            db.session.delete(chat)
            
            # Touch parent project
            self._touch_project(project_id)
            
            db.session.commit()
            
            self.logger.warning(
                f"Chat permanently deleted: {chat_id} by user {user_id}"
            )
            
            return ChatResult(
                success=True,
                message="Chat permanently deleted"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error permanently deleting chat: {str(e)}"
            self.logger.error(error_msg)
            return ChatResult(success=False, error=error_msg)

    def get_chat_statistics(self, user_id: int, 
                           project_id: Optional[int] = None) -> Dict:
        """
        Get statistics about user's chats
        
        Args:
            user_id: ID of the user
            project_id: Optional filter by project
            
        Returns:
            Dictionary with chat statistics
        """
        try:
            base_query = Chat.query.join(Project).filter(
                or_(
                    Project.created_by == user_id,  # User's own projects
                    Project.is_public == True        # Public projects
                )
            )
            
            if project_id:
                if not self._verify_project_access(project_id, user_id):
                    return {
                        'error': 'Project not found or access denied',
                        'total_chats': 0,
                        'active_chats': 0,
                        'deleted_chats': 0
                    }
                base_query = base_query.filter(Chat.project_id == project_id)
            
            total_chats = base_query.count()
            
            active_chats = base_query.filter(Chat.is_deleted == False).count()
            
            deleted_chats = base_query.filter(Chat.is_deleted == True).count()
            
            # Most recent chat
            recent_chat = base_query.filter(
                Chat.is_deleted == False
            ).order_by(Chat.created_at.desc()).first()
            
            return {
                'total_chats': total_chats,
                'active_chats': active_chats,
                'deleted_chats': deleted_chats,
                'most_recent': recent_chat.to_summary_dict() if recent_chat else None
            }
            
        except Exception as e:
            error_msg = f"Error getting statistics: {str(e)}"
            self.logger.error(error_msg)
            return {
                'total_chats': 0,
                'active_chats': 0,
                'deleted_chats': 0,
                'most_recent': None,
                'error': error_msg
            }

    def health_check(self) -> Dict:
        """
        Health check for chat service
        
        Returns:
            Dictionary with health status
        """
        try:
            # Test database connectivity
            chat_count = Chat.query.count()
            
            return {
                'status': 'healthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'total_chats_in_system': chat_count
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(UTC).isoformat(),
                'error': str(e)
            }


# Global instance
chat_service = ChatService()


