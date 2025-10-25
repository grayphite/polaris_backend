"""
OpenAI Chat Service - Business logic for OpenAI chat management

Handles CRUD operations for AI chat conversations with OpenAI integration.
Supports multiple AI models and providers with comprehensive statistics tracking.
"""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

import openai
from sqlalchemy import or_, and_
from src.extensions import db
from src.models.ai_chat import AIChat, AIStats
from src.models.chat import Chat
from src.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class AIChatResult:
    """Result of an AI chat operation"""
    success: bool
    ai_chat: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


@dataclass
class OpenAIResponse:
    """OpenAI API response wrapper"""
    success: bool
    content: Optional[str] = None
    usage: Optional[Dict] = None
    model: Optional[str] = None
    request_id: Optional[str] = None
    error: Optional[str] = None
    response_time_ms: Optional[int] = None


class OpenAIChatService:
    """Service for managing OpenAI chat conversations with full CRUD operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.openai_client = None
        self.api_key = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization of OpenAI client"""
        if self._initialized:
            return
            
        self.api_key = os.getenv('OPENAI_API_KEY')
        
        # Initialize OpenAI client if API key is available
        if self.api_key:
            try:
                # Initialize with explicit configuration to avoid proxy issues
                self.openai_client = openai.OpenAI(
                    api_key=self.api_key,
                    timeout=30.0,
                    http_client=None  # Use default HTTP client
                )
                self.logger.info("OpenAI client initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize OpenAI client: {str(e)}")
                # Try alternative initialization without any extra parameters
                try:
                    self.openai_client = openai.OpenAI(api_key=self.api_key)
                    self.logger.info("OpenAI client initialized with fallback method")
                except Exception as e2:
                    self.logger.error(f"Fallback initialization also failed: {str(e2)}")
                    # Try with explicit None for proxies
                    try:
                        import httpx
                        self.openai_client = openai.OpenAI(
                            api_key=self.api_key,
                            http_client=httpx.Client(proxies=None)
                        )
                        self.logger.info("OpenAI client initialized with httpx client")
                    except Exception as e3:
                        self.logger.error(f"httpx initialization also failed: {str(e3)}")
        else:
            self.logger.warning("OPENAI_API_KEY not found in environment variables")
            
        self._initialized = True

    def _verify_chat_access(self, chat_id: int, user_id: int) -> bool:
        """
        Verify user has access to the chat
        
        Args:
            chat_id: ID of the chat
            user_id: ID of the user
            
        Returns:
            True if user has access, False otherwise
        """
        chat = Chat.query.filter_by(
            id=chat_id,
            created_by=user_id,
            is_deleted=False
        ).first()
        return chat is not None

    def _touch_chat(self, chat_id: int):
        """
        Touch parent chat to update its updated_at timestamp
        
        Args:
            chat_id: ID of the chat to touch
        """
        try:
            chat = Chat.query.get(chat_id)
            if chat:
                chat.updated_at = datetime.now(timezone.utc)
        except Exception as e:
            self.logger.warning(f"Failed to touch chat {chat_id}: {str(e)}")

    def create_ai_chat(self, chat_id: int, user_id: int, user_question: str,
                      ai_model: str = "gpt-4.1", conversation_context: str = None,
                      context_limit: int = 10) -> AIChatResult:
        """
        Create a new AI chat conversation
        
        Args:
            chat_id: ID of the parent chat
            user_id: ID of the user
            user_question: User's question
            ai_model: AI model to use (default: gpt-4.1)
            conversation_context: Previous conversation context (if None, will auto-generate)
            context_limit: Number of recent conversations to include in context (default: 10)
            
        Returns:
            AIChatResult with success status and AI chat data
        """
        try:
            # Validate input
            if not user_question or not user_question.strip():
                return AIChatResult(
                    success=False,
                    error="User question is required"
                )
            
            if len(user_question) > 10000:
                return AIChatResult(
                    success=False,
                    error="User question is too long (max 10,000 characters)"
                )
            
            # Verify chat access
            if not self._verify_chat_access(chat_id, user_id):
                return AIChatResult(
                    success=False,
                    error="Chat not found or access denied"
                )
            
            # Generate previous context if not provided
            if not conversation_context:
                conversation_context = self.generate_previous_context(
                    chat_id=chat_id,
                    user_id=user_id,
                    context_limit=context_limit
                )
            
            # Get AI response from OpenAI
            openai_response = self._get_openai_response(
                user_question, ai_model, conversation_context
            )
            
            if not openai_response.success:
                return AIChatResult(
                    success=False,
                    error=f"OpenAI API error: {openai_response.error}"
                )
            
            # Check if this is the first AI chat in the conversation
            existing_ai_chats_count = AIChat.query.filter_by(
                chat_id=chat_id, 
                user_id=user_id, 
                is_deleted=False
            ).count()
            
            # Only generate chat name for the first AI chat to minimize AI load
            if existing_ai_chats_count == 0:
                chat_name = self.generate_chat_name(user_question.strip(), ai_model)
            else:
                chat_name = ""  # Empty string for subsequent AI chats
            
            # Create AI chat record
            ai_chat = AIChat(
                chat_id=chat_id,
                user_id=user_id,
                user_question=user_question.strip(),
                ai_answer=openai_response.content,
                chat_name=chat_name,
                ai_model=ai_model,
                ai_model_provider="OpenAI",
                conversation_context=conversation_context,
                context_metadata={
                    'api_version': 'v1',
                    'request_timestamp': datetime.now(timezone.utc).isoformat(),
                    'model_used': openai_response.model
                }
            )
            
            db.session.add(ai_chat)
            db.session.flush()  # Get the ID
            
            # Create AI stats record
            ai_stats = AIStats(
                ai_chat_id=ai_chat.id,
                tokens_used=openai_response.usage.get('total_tokens') if openai_response.usage else None,
                prompt_tokens=openai_response.usage.get('prompt_tokens') if openai_response.usage else None,
                completion_tokens=openai_response.usage.get('completion_tokens') if openai_response.usage else None,
                response_time_ms=openai_response.response_time_ms,
                api_version='v1',
                request_id=openai_response.request_id,
                error_occurred=not openai_response.success,
                error_message=openai_response.error if not openai_response.success else None
            )
            
            db.session.add(ai_stats)
            
            # Touch parent chat
            self._touch_chat(chat_id)
            
            db.session.commit()
            
            self.logger.info(f"AI chat created: {ai_chat.id} for chat {chat_id} by user {user_id}")
            
            return AIChatResult(
                success=True,
                ai_chat=ai_chat.to_dict(),
                message="AI chat created successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating AI chat: {str(e)}"
            self.logger.error(error_msg)
            return AIChatResult(success=False, error=error_msg)

    def get_ai_chat_by_id(self, ai_chat_id: int, user_id: int,
                          include_deleted: bool = False) -> Optional[Dict]:
        """
        Get a specific AI chat by ID
        
        Args:
            ai_chat_id: ID of the AI chat
            user_id: ID of the requesting user
            include_deleted: Whether to include soft-deleted AI chats
            
        Returns:
            AI chat dictionary or None if not found
        """
        try:
            query = AIChat.query.filter_by(id=ai_chat_id, user_id=user_id)
            
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            
            ai_chat = query.first()
            
            if not ai_chat:
                return None
            
            # Verify user has access to parent chat
            if not self._verify_chat_access(ai_chat.chat_id, user_id):
                return None
            
            return ai_chat.to_dict()
            
        except Exception as e:
            error_msg = f"Error fetching AI chat: {str(e)}"
            self.logger.error(error_msg)
            return None

    def list_ai_chats(self, chat_id: int, user_id: int, page: int = 1, per_page: int = 20,
                     search: str = None, include_deleted: bool = False) -> Dict:
        """
        List AI chats for a specific chat with pagination and search
        
        Args:
            chat_id: ID of the parent chat
            user_id: ID of the requesting user
            page: Page number (1-indexed)
            per_page: Items per page
            search: Optional search query
            include_deleted: Whether to include soft-deleted AI chats
            
        Returns:
            Dictionary with AI chats list and pagination metadata
        """
        try:
            # Verify user has access to parent chat
            if not self._verify_chat_access(chat_id, user_id):
                return {
                    'success': False,
                    'error': 'Chat not found or access denied',
                    'ai_chats': [],
                    'pagination': {}
                }
            
            # Start with AI chats for the specific chat
            query = AIChat.query.filter_by(chat_id=chat_id, user_id=user_id)
            
            # Filter deleted AI chats
            if not include_deleted:
                query = query.filter_by(is_deleted=False)
            
            # Search functionality
            if search and search.strip():
                search_term = f"%{search.strip()}%"
                query = query.filter(
                    or_(
                        AIChat.user_question.ilike(search_term),
                        AIChat.ai_answer.ilike(search_term),
                        AIChat.ai_model.ilike(search_term)
                    )
                )
            
            # Order by created_at descending
            query = query.order_by(AIChat.created_at.desc())
            
            # Paginate
            pagination = query.paginate(
                page=page,
                per_page=per_page,
                error_out=False
            )
            
            ai_chats = [ai_chat.to_dict() for ai_chat in pagination.items]
            
            return {
                'success': True,
                'ai_chats': ai_chats,
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
            error_msg = f"Error listing AI chats: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'ai_chats': [],
                'pagination': {}
            }

    def update_ai_chat(self, ai_chat_id: int, user_id: int,
                      data: Dict) -> AIChatResult:
        """
        Update an existing AI chat
        
        Args:
            ai_chat_id: ID of the AI chat to update
            user_id: ID of the requesting user
            data: Dictionary with fields to update
            
        Returns:
            AIChatResult with updated AI chat data
        """
        try:
            ai_chat = AIChat.query.filter_by(
                id=ai_chat_id,
                user_id=user_id,
                is_deleted=False
            ).first()
            
            if not ai_chat:
                return AIChatResult(
                    success=False,
                    error="AI chat not found"
                )
            
            # Verify user has access to parent chat
            if not self._verify_chat_access(ai_chat.chat_id, user_id):
                return AIChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Update allowed fields
            if 'user_question' in data:
                if not data['user_question'] or not data['user_question'].strip():
                    return AIChatResult(
                        success=False,
                        error="User question cannot be empty"
                    )
                ai_chat.user_question = data['user_question'].strip()
            
            if 'ai_answer' in data:
                ai_chat.ai_answer = data['ai_answer']
            
            if 'conversation_context' in data:
                ai_chat.conversation_context = data.get('conversation_context')
            
            if 'context_metadata' in data:
                ai_chat.context_metadata = data.get('context_metadata')
            
            ai_chat.updated_at = datetime.now(timezone.utc)
            
            # Touch parent chat
            self._touch_chat(ai_chat.chat_id)
            
            db.session.commit()
            
            self.logger.info(f"AI chat updated: {ai_chat.id} by user {user_id}")
            
            return AIChatResult(
                success=True,
                ai_chat=ai_chat.to_dict(),
                message="AI chat updated successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error updating AI chat: {str(e)}"
            self.logger.error(error_msg)
            return AIChatResult(success=False, error=error_msg)

    def delete_ai_chat(self, ai_chat_id: int, user_id: int) -> AIChatResult:
        """
        Soft delete an AI chat
        
        Args:
            ai_chat_id: ID of the AI chat to delete
            user_id: ID of the user deleting the AI chat
            
        Returns:
            AIChatResult indicating success or failure
        """
        try:
            ai_chat = AIChat.query.filter_by(
                id=ai_chat_id,
                user_id=user_id,
                is_deleted=False
            ).first()
            
            if not ai_chat:
                return AIChatResult(
                    success=False,
                    error="AI chat not found or already deleted"
                )
            
            # Verify user has access to parent chat
            if not self._verify_chat_access(ai_chat.chat_id, user_id):
                return AIChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Soft delete
            ai_chat.is_deleted = True
            ai_chat.deleted_at = datetime.now(timezone.utc)
            ai_chat.deleted_by = user_id
            ai_chat.updated_at = datetime.now(timezone.utc)
            
            # Touch parent chat
            self._touch_chat(ai_chat.chat_id)
            
            db.session.commit()
            
            self.logger.info(f"AI chat soft-deleted: {ai_chat.id} by user {user_id}")
            
            return AIChatResult(
                success=True,
                message="AI chat deleted successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error deleting AI chat: {str(e)}"
            self.logger.error(error_msg)
            return AIChatResult(success=False, error=error_msg)

    def restore_ai_chat(self, ai_chat_id: int, user_id: int) -> AIChatResult:
        """
        Restore a soft-deleted AI chat
        
        Args:
            ai_chat_id: ID of the AI chat to restore
            user_id: ID of the requesting user
            
        Returns:
            AIChatResult with restored AI chat data
        """
        try:
            ai_chat = AIChat.query.filter_by(
                id=ai_chat_id,
                user_id=user_id,
                is_deleted=True
            ).first()
            
            if not ai_chat:
                return AIChatResult(
                    success=False,
                    error="AI chat not found or not deleted"
                )
            
            # Verify user has access to parent chat
            if not self._verify_chat_access(ai_chat.chat_id, user_id):
                return AIChatResult(
                    success=False,
                    error="Access denied"
                )
            
            # Restore AI chat
            ai_chat.is_deleted = False
            ai_chat.deleted_at = None
            ai_chat.deleted_by = None
            ai_chat.updated_at = datetime.now(timezone.utc)
            
            # Touch parent chat
            self._touch_chat(ai_chat.chat_id)
            
            db.session.commit()
            
            self.logger.info(f"AI chat restored: {ai_chat.id} by user {user_id}")
            
            return AIChatResult(
                success=True,
                ai_chat=ai_chat.to_dict(),
                message="AI chat restored successfully"
            )
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error restoring AI chat: {str(e)}"
            self.logger.error(error_msg)
            return AIChatResult(success=False, error=error_msg)

    def get_ai_chat_statistics(self, user_id: int, chat_id: Optional[int] = None) -> Dict:
        """
        Get AI chat statistics for user
        
        Args:
            user_id: ID of the user
            chat_id: Optional filter by specific chat
            
        Returns:
            Dictionary with AI chat statistics
        """
        try:
            base_query = AIChat.query.filter_by(user_id=user_id)
            
            if chat_id:
                if not self._verify_chat_access(chat_id, user_id):
                    return {
                        'error': 'Chat not found or access denied',
                        'total_ai_chats': 0,
                        'active_ai_chats': 0,
                        'deleted_ai_chats': 0
                    }
                base_query = base_query.filter_by(chat_id=chat_id)
            
            total_ai_chats = base_query.count()
            active_ai_chats = base_query.filter_by(is_deleted=False).count()
            deleted_ai_chats = base_query.filter_by(is_deleted=True).count()
            
            # Get usage statistics
            usage_stats = db.session.query(
                db.func.sum(AIStats.tokens_used).label('total_tokens'),
                db.func.avg(AIStats.response_time_ms).label('avg_response_time'),
                db.func.sum(AIStats.cost_usd).label('total_cost')
            ).join(AIChat).filter(AIChat.user_id == user_id).first()
            
            # Get model distribution
            model_stats = db.session.query(
                AIChat.ai_model,
                AIChat.ai_model_provider,
                db.func.count(AIChat.id).label('count')
            ).filter_by(user_id=user_id, is_deleted=False).group_by(
                AIChat.ai_model, AIChat.ai_model_provider
            ).all()
            
            return {
                'total_ai_chats': total_ai_chats,
                'active_ai_chats': active_ai_chats,
                'deleted_ai_chats': deleted_ai_chats,
                'total_tokens_used': usage_stats.total_tokens or 0,
                'average_response_time_ms': round(usage_stats.avg_response_time or 0, 2),
                'total_cost_usd': float(usage_stats.total_cost or 0),
                'model_distribution': [
                    {
                        'model': stat.ai_model,
                        'provider': stat.ai_model_provider,
                        'count': stat.count
                    } for stat in model_stats
                ]
            }
            
        except Exception as e:
            error_msg = f"Error getting statistics: {str(e)}"
            self.logger.error(error_msg)
            return {
                'total_ai_chats': 0,
                'active_ai_chats': 0,
                'deleted_ai_chats': 0,
                'error': error_msg
            }

    def generate_previous_context(self, chat_id: int, user_id: int, 
                                 context_limit: int = 10) -> str:
        """
        Generate previous conversation context from recent AI chats
        
        Args:
            chat_id: ID of the chat to get context from
            user_id: ID of the user requesting context
            context_limit: Maximum number of recent AI chats to include (default: 10)
            
        Returns:
            Formatted context string for OpenAI model, or empty string if no context
        """
        try:
            # Validate input parameters
            if context_limit <= 0:
                self.logger.warning(f"Invalid context_limit {context_limit}, using default 10")
                context_limit = 10
            
            if context_limit > 50:  # Reasonable upper limit
                self.logger.warning(f"Context limit {context_limit} too high, capping at 50")
                context_limit = 50
            
            # Verify user has access to the chat
            if not self._verify_chat_access(chat_id, user_id):
                self.logger.warning(f"User {user_id} does not have access to chat {chat_id}")
                return ""
            
            # Query recent AI chats for this chat
            recent_chats = AIChat.query.filter_by(
                chat_id=chat_id,
                user_id=user_id,
                is_deleted=False
            ).order_by(
                AIChat.created_at.desc()
            ).limit(context_limit).all()
            
            if not recent_chats:
                self.logger.info(f"No previous AI chats found for chat {chat_id}")
                return ""
            
            # Format the context for OpenAI
            context_parts = []
            context_parts.append("Previous conversation context:")
            context_parts.append("")
            
            # Reverse to get chronological order (oldest first)
            for ai_chat in reversed(recent_chats):
                if ai_chat.user_question and ai_chat.ai_answer:
                    context_parts.append(f"User: {ai_chat.user_question}")
                    context_parts.append(f"Assistant: {ai_chat.ai_answer}")
                    context_parts.append("")  # Empty line for separation
            
            # Remove the last empty line
            if context_parts and context_parts[-1] == "":
                context_parts.pop()
            
            context_string = "\n".join(context_parts)
            
            self.logger.info(f"Generated context for chat {chat_id} with {len(recent_chats)} previous conversations")
            
            return context_string
            
        except Exception as e:
            error_msg = f"Error generating previous context: {str(e)}"
            self.logger.error(error_msg)
            return ""

    def generate_chat_name(self, user_question: str, model: str = "gpt-4.1") -> str:
        """
        Generate a concise 2-5 word name/label for the chat based on user question
        
        Args:
            user_question: User's question to generate name from
            model: AI model to use for name generation
            
        Returns:
            Generated chat name (2-5 words) or fallback name if generation fails
        """
        try:
            self._ensure_initialized()
            
            if not self.openai_client:
                self.logger.warning("OpenAI client not initialized, using fallback name")
                return self._generate_fallback_name(user_question)
            
            # Create a specific prompt for name generation
            name_prompt = f"""Generate a concise, descriptive name for this conversation based on the user's question. 
The name should be 2-5 words that capture the main topic or intent.
Do not include any formatting, quotes, or extra text - just return the name.

User question: {user_question}

Name:"""
            
            try:
                start_time = time.time()
                
                # Make API call for name generation
                response = self.openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that generates concise, descriptive names for conversations. Always respond with just the name, no additional text."},
                        {"role": "user", "content": name_prompt}
                    ],
                    max_tokens=20,  # Very short response
                    temperature=0.3  # Lower temperature for more consistent naming
                )
                
                response_time_ms = int((time.time() - start_time) * 1000)
                
                if response.choices and response.choices[0].message.content:
                    generated_name = response.choices[0].message.content.strip()
                    
                    # Clean up the response (remove quotes, extra formatting)
                    generated_name = generated_name.strip('"\'`').strip()
                    
                    # Validate length (2-5 words)
                    words = generated_name.split()
                    if 2 <= len(words) <= 5:
                        self.logger.info(f"Generated chat name: '{generated_name}' in {response_time_ms}ms")
                        return generated_name
                    else:
                        self.logger.warning(f"Generated name has {len(words)} words, using fallback")
                        return self._generate_fallback_name(user_question)
                else:
                    self.logger.warning("No content in OpenAI response for name generation")
                    return self._generate_fallback_name(user_question)
                    
            except Exception as e:
                self.logger.error(f"OpenAI API error during name generation: {str(e)}")
                return self._generate_fallback_name(user_question)
                
        except Exception as e:
            self.logger.error(f"Error generating chat name: {str(e)}")
            return self._generate_fallback_name(user_question)
    
    def _generate_fallback_name(self, user_question: str) -> str:
        """
        Generate a fallback name when OpenAI generation fails
        
        Args:
            user_question: User's question
            
        Returns:
            Fallback name based on question content
        """
        try:
            # Simple fallback: take first few words and clean them up
            words = user_question.split()[:3]  # Take first 3 words
            fallback_name = " ".join(words)
            
            # Clean up common words and make it more readable
            fallback_name = fallback_name.lower()
            fallback_name = fallback_name.replace("?", "").replace("!", "").replace(".", "")
            fallback_name = fallback_name.title()  # Capitalize first letter of each word
            
            # Ensure it's not too long
            if len(fallback_name) > 50:
                fallback_name = fallback_name[:47] + "..."
            
            self.logger.info(f"Generated fallback name: '{fallback_name}'")
            return fallback_name
            
        except Exception as e:
            self.logger.error(f"Error generating fallback name: {str(e)}")
            return "AI Chat"

    def _get_openai_response(self, user_question: str, model: str = "gpt-4.1",
                           conversation_context: str = None) -> OpenAIResponse:
        """
        Get response from OpenAI API
        
        Args:
            user_question: User's question
            model: OpenAI model to use
            conversation_context: Previous conversation context
            
        Returns:
            OpenAIResponse with API response data
        """
        self._ensure_initialized()
        
        if not self.openai_client:
            return OpenAIResponse(
                success=False,
                error="OpenAI client not initialized. Check OPENAI_API_KEY."
            )
        
        try:
            start_time = time.time()
            
            # Prepare messages
            messages = []
            
            # Create system prompt with instructions for clean, plain responses
            system_prompt = "You are a helpful AI assistant. Respond in plain, clean text format without any markdown formatting, bold text, bullet points, or special formatting. Keep your responses conversational and natural, as if you're having a real-time chat conversation."
            
            if conversation_context:
                # If conversation context is provided, combine it with system instructions
                full_system_content = f"{system_prompt}\n\n{conversation_context}"
                messages.append({"role": "system", "content": full_system_content})
            else:
                # Use only the system prompt if no context
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": user_question})
            
            # Make API call using new OpenAI API format
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=2000,
                temperature=0.7
            )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            return OpenAIResponse(
                success=True,
                content=response.choices[0].message.content,
                usage={
                    'total_tokens': response.usage.total_tokens,
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens
                } if response.usage else None,
                model=response.model,
                request_id=response.id,
                response_time_ms=response_time_ms
            )
            
        except Exception as e:
            error_msg = f"OpenAI API error: {str(e)}"
            self.logger.error(error_msg)
            return OpenAIResponse(
                success=False,
                error=error_msg
            )

    def health_check(self) -> Dict:
        """
        Health check for OpenAI chat service
        
        Returns:
            Dictionary with health status
        """
        self._ensure_initialized()
        
        try:
            # Test OpenAI API connectivity
            if self.openai_client:
                # Simple test call
                test_response = self._get_openai_response("Hello", "gpt-4.1.1")
                api_status = "healthy" if test_response.success else "unhealthy"
                api_error = test_response.error if not test_response.success else None
            else:
                api_status = "unavailable"
                api_error = "OpenAI client not initialized"
            
            return {
                'status': 'healthy' if api_status == "healthy" else 'degraded',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'openai_api_status': api_status,
                'openai_api_error': api_error,
                'api_key_configured': bool(self.api_key)
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }


# Global instance
openai_chat_service = OpenAIChatService()
