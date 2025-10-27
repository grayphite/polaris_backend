"""
Anthropic Chat Service - Business logic for Anthropic Claude chat management

Handles CRUD operations for AI chat conversations with Anthropic Claude integration.
Supports multiple AI models and providers with comprehensive statistics tracking.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

import requests
from sqlalchemy import or_, and_
from src.extensions import db
from src.models.ai_chat import AIChat, AIStats
from src.models.chat import Chat
from src.models.user import User
from src.services.tokenizer_service import tokenizer_service

logger = logging.getLogger(__name__)


@dataclass
class AIChatResult:
    """Result of an AI chat operation"""
    success: bool
    ai_chat: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None


@dataclass
class AnthropicResponse:
    """Anthropic Claude API response wrapper"""
    success: bool
    content: Optional[str] = None
    usage: Optional[Dict] = None
    model: Optional[str] = None
    request_id: Optional[str] = None
    error: Optional[str] = None
    response_time_ms: Optional[int] = None


class AnthropicChatService:
    """Service for managing Anthropic Claude chat conversations with full CRUD operations"""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-sonnet-4-5-20250929"
        self.max_tokens = 2000
        self._initialized = False

        # Streaming configuration (aligned with Anthropic production model)
        # Based on Anthropic's actual production capabilities for millions of users
        self.streaming_timeout = int(os.getenv('ANTHROPIC_STREAMING_TIMEOUT', '300'))  # 5 minutes (Anthropic's max)
        self.streaming_chunk_size = int(os.getenv('ANTHROPIC_STREAMING_CHUNK_SIZE', '4096'))  # 4KB chunks (optimal for SSE)
        self.max_concurrent_streams = int(os.getenv('ANTHROPIC_MAX_CONCURRENT_STREAMS', '1000'))  # Scale for millions
        # Compression disabled by default for streaming to avoid ERR_CONTENT_DECODING_FAILED
        self.enable_streaming_compression = os.getenv('ANTHROPIC_ENABLE_STREAMING_COMPRESSION', 'false').lower() == 'true'
        
        # Production-grade rate limiting (aligned with Anthropic's limits)
        self.streaming_rate_limit = int(os.getenv('ANTHROPIC_STREAMING_RATE_LIMIT', '100'))  # 100/hour per user
        self.regular_rate_limit = int(os.getenv('ANTHROPIC_REGULAR_RATE_LIMIT', '200'))  # 200/hour per user
        
        # Connection pooling for high-scale production
        self.connection_pool_size = int(os.getenv('ANTHROPIC_CONNECTION_POOL_SIZE', '50'))
        self.connection_pool_maxsize = int(os.getenv('ANTHROPIC_CONNECTION_POOL_MAXSIZE', '100'))
        
        # Memory optimization for millions of users
        self.stream_buffer_size = int(os.getenv('ANTHROPIC_STREAM_BUFFER_SIZE', '8192'))  # 8KB buffer
        self.max_stream_duration = int(os.getenv('ANTHROPIC_MAX_STREAM_DURATION', '600'))  # 10 minutes max
        
        # Anthropic API version alignment
        self.anthropic_version = "2023-06-01"  # Latest stable version
        self.anthropic_beta = "files-api-2025-04-14"  # Latest beta features

    def _ensure_initialized(self):
        """Lazy initialization of Anthropic client"""
        if self._initialized:
            return
            
        if not self.api_key:
            self.logger.warning("ANTHROPIC_API_KEY not found in environment variables")
        else:
            self.logger.info("Anthropic API key configured")
            
        self._initialized = True


    def _verify_chat_access(self, chat_id: int, user_id: int) -> bool:
        """
        Verify user has access to the chat (either owns it or it's from a public project)
        
        Args:
            chat_id: ID of the chat
            user_id: ID of the user
            
        Returns:
            True if user has access, False otherwise
        """
        chat = Chat.query.filter_by(
            id=chat_id,
            is_deleted=False
        ).first()
        
        if not chat:
            return False
        
        # Allow access if user owns the chat OR if the parent project is public
        return chat.created_by == user_id or chat.project.is_public

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

    def create_ai_chat_stream(self, chat_id: int, user_id: int, user_question: str,
                             conversation_context: str = None, context_limit: int = 10, 
                             file_references: list = None, file_reference_details: list = None,
                             use_rag: bool = False):
        """
        Create a streaming AI chat conversation
        
        Args:
            chat_id: ID of the parent chat
            user_id: ID of the user
            user_question: User's question
            conversation_context: Previous conversation context (if None, will auto-generate)
            context_limit: Number of recent conversations to include in context (default: 10)
            file_references: List of Anthropic file IDs to include in the conversation
            file_reference_details: Detailed file reference information
            use_rag: Whether to use RAG for context enhancement (default: False)
            
        Yields:
            Dict: Streaming response data with metadata
        """
        try:
            # Validate input
            if not user_question or not user_question.strip():
                yield {
                    "type": "error",
                    "error": {
                        "type": "validation_error",
                        "message": "User question is required"
                    }
                }
                return
            
            if len(user_question) > 10000:
                yield {
                    "type": "error",
                    "error": {
                        "type": "validation_error",
                        "message": "User question is too long (max 10,000 characters)"
                    }
                }
                return
            
            # Verify chat access
            if not self._verify_chat_access(chat_id, user_id):
                yield {
                    "type": "error",
                    "error": {
                        "type": "access_denied",
                        "message": "Chat not found or access denied"
                    }
                }
                return
            
            # Handle file_reference_details - extract file_references automatically
            if file_reference_details is not None:
                if not isinstance(file_reference_details, list) or not all(isinstance(it, dict) for it in file_reference_details):
                    yield {
                        "type": "error",
                        "error": {
                            "type": "validation_error",
                            "message": "file_reference_details must be a list of objects"
                        }
                    }
                    return
                
                # Extract file IDs from file_reference_details if file_references not provided
                if not file_references:
                    try:
                        file_references = [item.get('id') for item in file_reference_details if item.get('id')]
                        if not file_references:
                            yield {
                                "type": "error",
                                "error": {
                                    "type": "validation_error",
                                    "message": "file_reference_details objects must contain 'id' field"
                                }
                            }
                            return
                    except Exception as e:
                        yield {
                            "type": "error",
                            "error": {
                                "type": "validation_error",
                                "message": f"Error extracting file IDs from file_reference_details: {str(e)}"
                            }
                        }
                        return
            
            # Validate file references if provided
            if file_references and not isinstance(file_references, list):
                yield {
                    "type": "error",
                    "error": {
                        "type": "validation_error",
                        "message": "file_references must be a list of file IDs"
                    }
                }
                return
            
            # Generate previous context if not provided
            if not conversation_context:
                conversation_context = self.generate_previous_context(
                    chat_id=chat_id,
                    user_id=user_id,
                    context_limit=context_limit
                )
            
            # RAG Enhancement (if enabled)
            rag_metadata = {}
            if use_rag:
                try:
                    # Use system defaults for RAG parameters
                    rag_result = self._try_rag_enhancement(
                        user_question=user_question,
                        similarity_threshold=None,  # Use system default
                        max_chunks=None,  # Use system default
                        rag_sources=None
                    )
                    if rag_result['success']:
                        # Enhance conversation context with RAG
                        conversation_context = self._enhance_context_with_rag(
                            conversation_context, 
                            rag_result
                        )
                        rag_metadata = rag_result.get('metadata', {})
                    else:
                        rag_metadata = {
                            'rag_enabled': False,
                            'fallback_reason': rag_result.get('error', 'RAG failed'),
                            'processing_mode': 'fallback'
                        }
                except Exception as e:
                    self.logger.warning(f"RAG enhancement failed: {str(e)}")
                    rag_metadata = {
                        'rag_enabled': False,
                        'fallback_reason': f'RAG error: {str(e)}',
                        'processing_mode': 'error'
                    }
            else:
                rag_metadata = {
                    'rag_enabled': False,
                    'fallback_reason': 'RAG not requested',
                    'processing_mode': 'normal'
                }
            
            # Get system prompt from prompts module
            # Use adaptive prompt for both tax and general questions
            from src.prompts.adaptive_system_prompt import get_adaptive_system_prompt, detect_question_type
            
            # Prepare RAG sources for prompt enhancement
            rag_sources = []
            if rag_metadata and rag_metadata.get('rag_enabled'):
                context_chunks = rag_metadata.get('context_chunks', [])
                rag_sources = context_chunks
            
            # Detect question type and get adaptive system prompt
            question_type = detect_question_type(user_question)
            system_context = get_adaptive_system_prompt(
                conversation_context=conversation_context,
                rag_metadata=rag_metadata,
                question_type=question_type
            )
            
            optimized_context, token_usage, truncation_result = tokenizer_service.optimize_context_for_request(
                user_question=user_question,
                context=conversation_context,
                file_references=file_references,
                model=self.model,
                system_prompt=system_context
            )
            
            # Log token usage and optimization
            self.logger.info(f"Token usage - Total: {token_usage.total_tokens}, "
                           f"Context: {token_usage.context_tokens}, "
                           f"User question: {token_usage.user_question_tokens}, "
                           f"File refs: {token_usage.file_references_tokens}")
            
            if truncation_result.messages_skipped > 0:
                self.logger.info(f"Context truncated: {truncation_result.messages_skipped} messages skipped, "
                               f"{truncation_result.tokens_saved} tokens saved")
            
            # Send initial metadata
            yield {
                "type": "stream_start",
                "metadata": {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "model": self.model,
                    "token_usage": {
                        'total_tokens': token_usage.total_tokens,
                        'context_tokens': token_usage.context_tokens,
                        'user_question_tokens': token_usage.user_question_tokens,
                        'file_references_tokens': token_usage.file_references_tokens,
                        'system_prompt_tokens': token_usage.system_prompt_tokens
                    },
                    'context_optimization': {
                        'messages_included': truncation_result.messages_included,
                        'messages_skipped': truncation_result.messages_skipped,
                        'tokens_saved': truncation_result.tokens_saved,
                        'context_truncated': truncation_result.messages_skipped > 0
                    },
                    'rag_metadata': rag_metadata
                }
            }
            
            # Stream response from Anthropic
            accumulated_content = ""
            usage_data = {}
            model_info = None
            request_id = None
            
            for event in self._get_anthropic_response_stream(
                user_question,
                self.model,
                optimized_context,
                file_references,
                file_reference_details=file_reference_details
            ):
                # Handle different event types
                if event.get("type") == "error":
                    yield event
                    return
                elif event.get("type") == "stream_end":
                    break
                elif event.get("type") == "content_block_delta":
                    # Accumulate content for final storage
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        accumulated_content += delta.get("text", "")
                        yield event
                elif event.get("type") == "message_delta":
                    # Update usage data
                    delta = event.get("delta", {})
                    if "usage" in delta:
                        usage_data.update(delta["usage"])
                elif event.get("type") == "message_start":
                    # Extract model and request info
                    message = event.get("message", {})
                    model_info = message.get("model")
                    request_id = message.get("id")
                else:
                    # Pass through other events
                    yield event
            
            # Check if this is the first AI chat in the conversation
            existing_ai_chats_count = AIChat.query.filter_by(
                chat_id=chat_id, 
                user_id=user_id, 
                is_deleted=False
            ).count()
            
            # Only generate chat name for the first AI chat to minimize AI load
            if existing_ai_chats_count == 0:
                chat_name = self.generate_chat_name(user_question.strip(), self.model)
            else:
                chat_name = ""  # Empty string for subsequent AI chats
            
            # Create AI chat record (only after streaming is complete)
            try:
                ai_chat = AIChat(
                    chat_id=chat_id,
                    user_id=user_id,
                    user_question=user_question.strip(),
                    ai_answer=accumulated_content,
                    chat_name=chat_name,
                    ai_model=self.model,
                    ai_model_provider="Anthropic",
                    conversation_context=conversation_context,
                    file_references=json.dumps(file_references) if file_references else None,
                    file_reference_details=json.dumps(file_reference_details) if file_reference_details else None,
                    context_metadata={
                        'api_version': '2023-06-01',
                        'request_timestamp': datetime.now(timezone.utc).isoformat(),
                        'model_used': self.model,
                        'file_count': len(file_references) if file_references else 0,
                        'token_usage': {
                            'total_tokens': token_usage.total_tokens,
                            'context_tokens': token_usage.context_tokens,
                            'user_question_tokens': token_usage.user_question_tokens,
                            'file_references_tokens': token_usage.file_references_tokens,
                            'system_prompt_tokens': token_usage.system_prompt_tokens
                        },
                        'context_optimization': {
                            'messages_included': truncation_result.messages_included,
                            'messages_skipped': truncation_result.messages_skipped,
                            'tokens_saved': truncation_result.tokens_saved,
                            'context_truncated': truncation_result.messages_skipped > 0
                        }
                    }
                )
                
                db.session.add(ai_chat)
                db.session.flush()  # Get the ID
                
                # Create AI stats record
                ai_stats = AIStats(
                    ai_chat_id=ai_chat.id,
                    tokens_used=usage_data.get('input_tokens', 0) + usage_data.get('output_tokens', 0) if usage_data else None,
                    prompt_tokens=usage_data.get('input_tokens') if usage_data else None,
                    completion_tokens=usage_data.get('output_tokens') if usage_data else None,
                    response_time_ms=None,  # Will be calculated from streaming
                    api_version='2023-06-01',
                    request_id=request_id,
                    error_occurred=False,
                    error_message=None
                )
                
                db.session.add(ai_stats)
                
                # Touch parent chat
                self._touch_chat(chat_id)
                
                db.session.commit()
                
                # Send final success event
                yield {
                    "type": "stream_complete",
                    "ai_chat": ai_chat.to_dict(),
                    "message": "AI chat created successfully",
                    "rag_metadata": rag_metadata
                }
                
                self.logger.info(f"Streaming AI chat created: {ai_chat.id} for chat {chat_id} by user {user_id}")
                
            except Exception as e:
                db.session.rollback()
                error_msg = f"Error saving AI chat after streaming: {str(e)}"
                self.logger.error(error_msg)
                yield {
                    "type": "error",
                    "error": {
                        "type": "database_error",
                        "message": error_msg
                    }
                }
            
        except Exception as e:
            error_msg = f"Error in streaming AI chat: {str(e)}"
            self.logger.error(error_msg)
            yield {
                "type": "error",
                "error": {
                    "type": "unexpected_error",
                    "message": error_msg
                }
            }

    def create_ai_chat(self, chat_id: int, user_id: int, user_question: str,
                      conversation_context: str = None, context_limit: int = 10, 
                      file_references: list = None, file_reference_details: list = None) -> AIChatResult:
        """
        Create a new AI chat conversation
        
        Args:
            chat_id: ID of the parent chat
            user_id: ID of the user
            user_question: User's question
            conversation_context: Previous conversation context (if None, will auto-generate)
            context_limit: Number of recent conversations to include in context (default: 10)
            file_references: List of Anthropic file IDs to include in the conversation
            
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
            
            # Handle file_reference_details - extract file_references automatically
            if file_reference_details is not None:
                if not isinstance(file_reference_details, list) or not all(isinstance(it, dict) for it in file_reference_details):
                    return AIChatResult(
                        success=False,
                        error="file_reference_details must be a list of objects"
                    )
                
                # Extract file IDs from file_reference_details if file_references not provided
                if not file_references:
                    try:
                        file_references = [item.get('id') for item in file_reference_details if item.get('id')]
                        if not file_references:
                            return AIChatResult(
                                success=False,
                                error="file_reference_details objects must contain 'id' field"
                            )
                    except Exception as e:
                        return AIChatResult(
                            success=False,
                            error=f"Error extracting file IDs from file_reference_details: {str(e)}"
                        )
            
            # Validate file references if provided (simplified validation)
            if file_references and not isinstance(file_references, list):
                return AIChatResult(
                    success=False,
                    error="file_references must be a list of file IDs"
                )
            
            # Generate previous context if not provided
            if not conversation_context:
                conversation_context = self.generate_previous_context(
                    chat_id=chat_id,
                    user_id=user_id,
                    context_limit=context_limit
                )
            
            # Get system prompt from prompts module
            # Use tax agent prompt for consistent tax-specific responses
            from src.prompts.adaptive_system_prompt import get_adaptive_system_prompt, detect_question_type
            
            # Detect question type and get adaptive system prompt
            question_type = detect_question_type(user_question)
            system_context = get_adaptive_system_prompt(
                conversation_context=conversation_context,
                question_type=question_type
            )
            optimized_context, token_usage, truncation_result = tokenizer_service.optimize_context_for_request(
                user_question=user_question,
                context=conversation_context,
                file_references=file_references,
                model=self.model,
                system_prompt=system_context
            )
            
            # Log token usage and optimization
            self.logger.info(f"Token usage - Total: {token_usage.total_tokens}, "
                           f"Context: {token_usage.context_tokens}, "
                           f"User question: {token_usage.user_question_tokens}, "
                           f"File refs: {token_usage.file_references_tokens}")
            
            if truncation_result.messages_skipped > 0:
                self.logger.info(f"Context truncated: {truncation_result.messages_skipped} messages skipped, "
                               f"{truncation_result.tokens_saved} tokens saved")
            
            # Get AI response from Anthropic Claude
            anthropic_response = self._get_anthropic_response(
                user_question,
                self.model,
                optimized_context,
                file_references,
                file_reference_details=file_reference_details
            )
            
            if not anthropic_response.success:
                return AIChatResult(
                    success=False,
                    error=f"Anthropic API error: {anthropic_response.error}"
                )
            
            # Check if this is the first AI chat in the conversation
            existing_ai_chats_count = AIChat.query.filter_by(
                chat_id=chat_id, 
                user_id=user_id, 
                is_deleted=False
            ).count()
            
            # Only generate chat name for the first AI chat to minimize AI load
            if existing_ai_chats_count == 0:
                chat_name = self.generate_chat_name(user_question.strip(), self.model)
            else:
                chat_name = ""  # Empty string for subsequent AI chats
            
            # Create AI chat record
            ai_chat = AIChat(
                chat_id=chat_id,
                user_id=user_id,
                user_question=user_question.strip(),
                ai_answer=anthropic_response.content,
                chat_name=chat_name,
                ai_model=self.model,
                ai_model_provider="Anthropic",
                conversation_context=conversation_context,
                file_references=json.dumps(file_references) if file_references else None,
                file_reference_details=json.dumps(file_reference_details) if file_reference_details else None,
                context_metadata={
                    'api_version': '2023-06-01',
                    'request_timestamp': datetime.now(timezone.utc).isoformat(),
                    'model_used': self.model,
                    'file_count': len(file_references) if file_references else 0,
                    'token_usage': {
                        'total_tokens': token_usage.total_tokens,
                        'context_tokens': token_usage.context_tokens,
                        'user_question_tokens': token_usage.user_question_tokens,
                        'file_references_tokens': token_usage.file_references_tokens,
                        'system_prompt_tokens': token_usage.system_prompt_tokens
                    },
                    'context_optimization': {
                        'messages_included': truncation_result.messages_included,
                        'messages_skipped': truncation_result.messages_skipped,
                        'tokens_saved': truncation_result.tokens_saved,
                        'context_truncated': truncation_result.messages_skipped > 0
                    }
                }
            )
            
            db.session.add(ai_chat)
            db.session.flush()  # Get the ID
            
            # Create AI stats record
            ai_stats = AIStats(
                ai_chat_id=ai_chat.id,
                tokens_used=anthropic_response.usage.get('input_tokens', 0) + anthropic_response.usage.get('output_tokens', 0) if anthropic_response.usage else None,
                prompt_tokens=anthropic_response.usage.get('input_tokens') if anthropic_response.usage else None,
                completion_tokens=anthropic_response.usage.get('output_tokens') if anthropic_response.usage else None,
                response_time_ms=anthropic_response.response_time_ms,
                api_version='2023-06-01',
                request_id=anthropic_response.request_id,
                error_occurred=not anthropic_response.success,
                error_message=anthropic_response.error if not anthropic_response.success else None
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
            Formatted context string for Anthropic Claude model, or empty string if no context
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
            
            # Format the context for Anthropic Claude
            context_parts = []
            context_parts.append("Previous conversation context:")
            context_parts.append("")
            
            # Reverse to get chronological order (oldest first)
            for ai_chat in reversed(recent_chats):
                if ai_chat.user_question and ai_chat.ai_answer:
                    context_parts.append(f"Human: {ai_chat.user_question}")
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

    def generate_chat_name(self, user_question: str, model: str = "claude-3-haiku-20240307") -> str:
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
            
            if not self.api_key:
                self.logger.warning("Anthropic API key not configured, using fallback name")
                return self._generate_fallback_name(user_question)
            
            # Create a specific prompt for name generation (legal-focused)
            name_prompt = f"""Generate a concise, descriptive name for this legal conversation based on the user's question. 
The name should be 2-5 words that capture the main legal topic, document type, or legal issue.
Focus on legal terminology and concepts. Do not include any formatting, quotes, or extra text - just return the name.

User question: {user_question}

Name:"""
            
            try:
                start_time = time.time()
                
                # Make API call for name generation
                response = self._get_anthropic_response(name_prompt, model)
                
                if response.success and response.content:
                    generated_name = response.content.strip()
                    
                    # Clean up the response (remove quotes, extra formatting)
                    generated_name = generated_name.strip('"\'`').strip()
                    
                    # Validate length (2-5 words)
                    words = generated_name.split()
                    if 2 <= len(words) <= 5:
                        self.logger.info(f"Generated chat name: '{generated_name}' in {response.response_time_ms}ms")
                        return generated_name
                    else:
                        self.logger.warning(f"Generated name has {len(words)} words, using fallback")
                        return self._generate_fallback_name(user_question)
                else:
                    self.logger.warning("No content in Anthropic response for name generation")
                    return self._generate_fallback_name(user_question)
                    
            except Exception as e:
                self.logger.error(f"Anthropic API error during name generation: {str(e)}")
                return self._generate_fallback_name(user_question)
                
        except Exception as e:
            self.logger.error(f"Error generating chat name: {str(e)}")
            return self._generate_fallback_name(user_question)
    
    def _generate_fallback_name(self, user_question: str) -> str:
        """
        Generate a fallback name when Anthropic generation fails
        
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

    def _get_anthropic_response_stream(self, user_question: str, model: str = "claude-sonnet-4-5-20250929",
                                      conversation_context: str = None, file_references: list = None,
                                      file_reference_details: Optional[List[Dict]] = None):
        """
        Get streaming response from Anthropic Claude API using Server-Sent Events (SSE)
        
        Args:
            user_question: User's question
            model: Anthropic model to use
            conversation_context: Previous conversation context
            file_references: List of Anthropic file IDs to include in the conversation
            file_reference_details: Detailed file reference information
            
        Yields:
            Dict: SSE event data from Anthropic API
        """
        self._ensure_initialized()
        
        if not self.api_key:
            yield {
                "type": "error",
                "error": {
                    "type": "api_key_missing",
                    "message": "Anthropic API key not configured"
                }
            }
            return
        
        try:
            start_time = time.time()
            
            # Get system prompt from prompts module
            from src.prompts.adaptive_system_prompt import get_adaptive_system_prompt, detect_question_type
            
            # Get system prompt
            question_type = detect_question_type(user_question)
            system_context = get_adaptive_system_prompt(
                conversation_context=conversation_context,
                question_type=question_type
            )

            # Build the user message content
            if conversation_context:
                full_prompt = f"{conversation_context}\n\nHuman: {user_question}\n\nAssistant:"
            else:
                full_prompt = f"Human: {user_question}\n\nAssistant:"
            
            # Prepare headers with production-grade settings
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
                "anthropic-beta": self.anthropic_beta
            }
            
            # Prepare message content (same logic as non-streaming)
            message_content = []

            # Add file references if provided
            if file_reference_details and isinstance(file_reference_details, list):
                for item in file_reference_details:
                    try:
                        file_id = item.get('id') or item.get('file_id')
                        if not file_id:
                            continue
                        mime_type = item.get('mime') or item.get('mime_type') or ''
                        if isinstance(mime_type, str) and mime_type.startswith('image/'):
                            message_content.append({
                                "type": "image",
                                "source": {
                                    "type": "file",
                                    "file_id": file_id
                                }
                            })
                        else:
                            message_content.append({
                                "type": "document",
                                "source": {
                                    "type": "file",
                                    "file_id": file_id
                                }
                            })
                    except Exception:
                        fid = item.get('id') or item.get('file_id')
                        if fid:
                            message_content.append({
                                "type": "document",
                                "source": {
                                    "type": "file",
                                    "file_id": fid
                                }
                            })
            elif file_references:
                for file_id in file_references:
                    message_content.append({
                        "type": "document",
                        "source": {
                            "type": "file",
                            "file_id": file_id
                        }
                    })
            
            # Add text content
            message_content.append({
                "type": "text",
                "text": full_prompt
            })
            
            # Prepare payload with streaming enabled
            payload = {
                "model": model,
                "max_tokens": self.max_tokens,
                "system": system_context,
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ],
                "stream": True  # Enable streaming
            }
            
            # Make streaming API call
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=True,  # Enable streaming
                timeout=self.streaming_timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Anthropic API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                yield {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": error_msg,
                        "status_code": response.status_code
                    }
                }
                return
            
            # Parse SSE events with production-grade buffering
            buffer = ""
            for chunk in response.iter_content(chunk_size=self.streaming_chunk_size, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line.startswith('data: '):
                            data_content = line[6:]  # Remove 'data: ' prefix
                            
                            if data_content == '[DONE]':
                                yield {
                                    "type": "stream_end",
                                    "message": "Stream completed successfully"
                                }
                                return
                            
                            try:
                                event_data = json.loads(data_content)
                                # Add metadata
                                event_data['_metadata'] = {
                                    'timestamp': time.time(),
                                    'elapsed_ms': int((time.time() - start_time) * 1000)
                                }
                                yield event_data
                            except json.JSONDecodeError as e:
                                self.logger.warning(f"Failed to parse SSE data: {data_content[:100]}... Error: {str(e)}")
                                continue
                        elif line.startswith('event: '):
                            # Handle event type
                            event_type = line[7:]
                            continue
                        elif line == '':
                            # Empty line, continue
                            continue
                        else:
                            # Other SSE content
                            continue
            
            # Handle any remaining buffer
            if buffer.strip():
                self.logger.warning(f"Unprocessed buffer content: {buffer[:100]}...")
            
        except requests.exceptions.Timeout:
            error_msg = "Timeout communicating with Anthropic API during streaming"
            self.logger.error(error_msg)
            yield {
                "type": "error",
                "error": {
                    "type": "timeout",
                    "message": error_msg
                }
            }
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error during streaming: {str(e)}"
            self.logger.error(error_msg)
            yield {
                "type": "error",
                "error": {
                    "type": "connection_error",
                    "message": error_msg
                }
            }
        except Exception as e:
            error_msg = f"Unexpected error during streaming: {str(e)}"
            self.logger.error(error_msg)
            yield {
                "type": "error",
                "error": {
                    "type": "unexpected_error",
                    "message": error_msg
                }
            }

    def _get_anthropic_response(self, user_question: str, model: str = "claude-3-haiku-20240307",
                               conversation_context: str = None, file_references: list = None,
                               file_reference_details: Optional[List[Dict]] = None) -> AnthropicResponse:
        """
        Get response from Anthropic Claude API
        
        Args:
            user_question: User's question
            model: Anthropic model to use
            conversation_context: Previous conversation context
            file_references: List of Anthropic file IDs to include in the conversation
            
        Returns:
            AnthropicResponse with API response data
        """
        self._ensure_initialized()
        
        if not self.api_key:
            return AnthropicResponse(
                success=False,
                error="Anthropic API key not configured. Check ANTHROPIC_API_KEY."
            )
        
        try:
            start_time = time.time()
            
            # Get system prompt from prompts module
            from src.prompts.adaptive_system_prompt import get_adaptive_system_prompt, detect_question_type
            
            # Get system prompt
            question_type = detect_question_type(user_question)
            system_context = get_adaptive_system_prompt(
                conversation_context=conversation_context,
                question_type=question_type
            )

            # Build the user message content (no system text embedded)
            if conversation_context:
                full_prompt = f"{conversation_context}\n\nHuman: {user_question}\n\nAssistant:"
            else:
                full_prompt = f"Human: {user_question}\n\nAssistant:"
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "files-api-2025-04-14"
            }
            
            # Prepare message content
            message_content = []

            # Add file references if provided
            # If we have rich details, use mime_type to choose between document vs image blocks
            if file_reference_details and isinstance(file_reference_details, list):
                for item in file_reference_details:
                    try:
                        file_id = item.get('id') or item.get('file_id')
                        if not file_id:
                            continue
                        mime_type = item.get('mime') or item.get('mime_type') or ''
                        if isinstance(mime_type, str) and mime_type.startswith('image/'):
                            # Send as image block per Claude Files API docs
                            message_content.append({
                                "type": "image",
                                "source": {
                                    "type": "file",
                                    "file_id": file_id
                                }
                            })
                        else:
                            # Default to document block for PDFs/plain text
                            message_content.append({
                                "type": "document",
                                "source": {
                                    "type": "file",
                                    "file_id": file_id
                                }
                            })
                    except Exception:
                        # Fallback to document block if anything goes wrong
                        fid = item.get('id') or item.get('file_id')
                        if fid:
                            message_content.append({
                                "type": "document",
                                "source": {
                                    "type": "file",
                                    "file_id": fid
                                }
                            })
            elif file_references:
                # Backward-compatible behavior: assume document blocks for all
                for file_id in file_references:
                    message_content.append({
                        "type": "document",
                        "source": {
                            "type": "file",
                            "file_id": file_id
                        }
                    })
            
            # Add text content
            message_content.append({
                "type": "text",
                "text": full_prompt
            })
            
            # Prepare payload
            payload = {
                "model": model,
                "max_tokens": self.max_tokens,
                "system": system_context,
                "messages": [
                    {
                        "role": "user",
                        "content": message_content
                    }
                ]
            }
            
            # Make API call
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response_time_ms = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                data = response.json()
                content = data.get('content', [{}])[0].get('text', '')
                usage = data.get('usage', {})
                
                return AnthropicResponse(
                    success=True,
                    content=content,
                    usage=usage,
                    model=data.get('model'),
                    request_id=data.get('id'),
                    response_time_ms=response_time_ms
                )
            else:
                error_msg = f"Anthropic API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)
                return AnthropicResponse(
                    success=False,
                    error=error_msg,
                    response_time_ms=response_time_ms
                )
            
        except requests.exceptions.Timeout:
            error_msg = "Timeout communicating with Anthropic API"
            self.logger.error(error_msg)
            return AnthropicResponse(
                success=False,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Anthropic API error: {str(e)}"
            self.logger.error(error_msg)
            return AnthropicResponse(
                success=False,
                error=error_msg
            )

    def health_check(self) -> Dict:
        """
        Health check for Anthropic chat service
        
        Returns:
            Dictionary with health status
        """
        self._ensure_initialized()
        
        try:
            # Test Anthropic API connectivity
            if self.api_key:
                # Simple test call
                test_response = self._get_anthropic_response("Hello", "claude-3-haiku-20240307")
                api_status = "healthy" if test_response.success else "unhealthy"
                api_error = test_response.error if not test_response.success else None
            else:
                api_status = "unavailable"
                api_error = "Anthropic API key not configured"
            
            return {
                'status': 'healthy' if api_status == "healthy" else 'degraded',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'anthropic_api_status': api_status,
                'anthropic_api_error': api_error,
                'api_key_configured': bool(self.api_key)
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }

    def _try_rag_enhancement(self, user_question: str, similarity_threshold: float = None, 
                           max_chunks: int = None, rag_sources: list = None) -> Dict[str, Any]:
        """
        Try to enhance context using RAG
        
        Args:
            user_question: User's question
            similarity_threshold: RAG similarity threshold
            max_chunks: Maximum RAG chunks
            rag_sources: Optional specific sources
            
        Returns:
            Dict with RAG result and metadata
        """
        try:
            # Import RAG components safely
            from src.services.rag_claude_middleware import get_rag_claude_middleware
            
            middleware = get_rag_claude_middleware()
            if not middleware.rag_enabled:
                return {
                    'success': False,
                    'error': 'RAG not available',
                    'metadata': {
                        'rag_enabled': False,
                        'fallback_reason': 'RAG middleware not available'
                    }
                }
            
            # Use system defaults if parameters not provided
            if similarity_threshold is None:
                # Load from RAG config
                try:
                    from rag.config.rag_config import get_rag_config_values
                    config = get_rag_config_values()
                    similarity_threshold = config.search.default_score_threshold
                except:
                    similarity_threshold = 0.01  # Fallback default
            
            if max_chunks is None:
                # Load from RAG config
                try:
                    from rag.config.rag_config import get_rag_config_values
                    config = get_rag_config_values()
                    max_chunks = config.search.default_max_docs
                except:
                    max_chunks = 5  # Fallback default
            
            # Try RAG query
            rag_result = middleware.rag_integration.juridical_query(
                query=user_question,
                max_chunks=max_chunks,
                similarity_threshold=similarity_threshold
            )
            
            if rag_result.get('success', False):
                return {
                    'success': True,
                    'context_chunks': rag_result.get('context_chunks', []),
                    'sources': rag_result.get('sources', []),
                    'metadata': {
                        'rag_enabled': True,
                        'processing_mode': 'rag_enhanced',
                        'docs_found': len(rag_result.get('context_chunks', [])),
                        'sources': rag_result.get('sources', []),
                        'max_relevance_score': max([chunk.get('score', 0) for chunk in rag_result.get('context_chunks', [])], default=0)
                    }
                }
            else:
                return {
                    'success': False,
                    'error': rag_result.get('error', 'RAG query failed'),
                    'metadata': {
                        'rag_enabled': False,
                        'fallback_reason': rag_result.get('error', 'RAG query failed')
                    }
                }
                
        except Exception as e:
            self.logger.warning(f"RAG enhancement error: {str(e)}")
            return {
                'success': False,
                'error': f'RAG error: {str(e)}',
                'metadata': {
                    'rag_enabled': False,
                    'fallback_reason': f'RAG error: {str(e)}'
                }
            }
    
    def _enhance_context_with_rag(self, conversation_context: str, rag_result: Dict[str, Any]) -> str:
        """
        Enhance conversation context with RAG results
        
        Args:
            conversation_context: Original conversation context
            rag_result: RAG enhancement result
            
        Returns:
            Enhanced conversation context
        """
        try:
            context_chunks = rag_result.get('context_chunks', [])
            sources = rag_result.get('sources', [])
            
            if not context_chunks:
                return conversation_context
            
            # Build RAG context section
            rag_context = "\n\n=== RAG ENHANCED CONTEXT ===\n"
            rag_context += "Relevant legal documents found:\n"
            
            for i, chunk in enumerate(context_chunks, 1):
                source = chunk.get('source', 'Unknown')
                score = chunk.get('score', 0)
                text = chunk.get('text', '')[:500]  # Limit text length
                
                rag_context += f"\n{i}. Source: {source} (Relevance: {score:.3f})\n"
                rag_context += f"Content: {text}...\n"
            
            rag_context += f"\nSources: {', '.join(sources)}\n"
            rag_context += "=== END RAG CONTEXT ===\n"
            
            # Combine with existing context
            enhanced_context = conversation_context + rag_context
            return enhanced_context
            
        except Exception as e:
            self.logger.warning(f"Error enhancing context with RAG: {str(e)}")
            return conversation_context


# Global instance
anthropic_chat_service = AnthropicChatService()
