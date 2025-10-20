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
            
            # Optimize context using tokenizer service (pass the same system prompt we'll use)
            system_context = (
                "You are a specialized legal AI assistant designed to analyze legal documents and provide accurate "
                "legal information. Your purpose is to assist legal professionals and individuals seeking legal understanding.\n\n"
                "CORE PRINCIPLES:\n"
                "- Provide precise, legally accurate information based on established legal principles\n"
                "- Focus on objective legal analysis without offering specific legal advice or attorney-client relationships\n"
                "- Maintain professional, clear language appropriate for legal contexts\n"
                "- Cite relevant statutes, regulations, case law, or legal precedents when applicable\n"
                "- Acknowledge jurisdictional variations and limitations in your knowledge\n\n"
                "RESPONSE FORMAT:\n"
                "- Use plain text only (no markdown, bullet points, or special formatting)\n"
                "- Be concise yet comprehensive enough to address the legal query fully\n"
                "- Structure responses logically: key findings first, followed by supporting details\n"
                "- Use clear paragraph breaks for readability\n\n"
                "DOCUMENT ANALYSIS APPROACH:\n"
                "When analyzing legal documents, identify and explain:\n"
                "- Main legal purpose and document type\n"
                "- Key parties, roles, and their obligations\n"
                "- Critical terms, conditions, and requirements\n"
                "- Important dates, deadlines, and time-sensitive provisions\n"
                "- Legal rights, remedies, and liabilities\n"
                "- Potential legal risks, ambiguities, or areas requiring attention\n"
                "- Relevant jurisdictional law or governing provisions\n"
                "- Cross-references to related clauses or external legal requirements\n\n"
                "GENERAL LEGAL QUESTIONS:\n"
                "When answering legal questions:\n"
                "- Provide clear explanations of legal concepts and terminology\n"
                "- Reference applicable laws, regulations, or legal standards\n"
                "- Distinguish between general legal principles and jurisdiction-specific rules\n"
                "- Explain practical implications and typical legal outcomes\n"
                "- Identify when professional legal counsel should be consulted\n\n"
                "CRITICAL LIMITATIONS:\n"
                "- Always clarify that you do not provide legal advice or replace qualified legal counsel\n"
                "- State when information may be jurisdiction-dependent or time-sensitive\n"
                "- Acknowledge gaps in your knowledge or when updated legal research is needed\n"
                "- Never guarantee legal outcomes or suggest specific legal strategies for individual cases\n"
                "- Recommend consulting a licensed attorney for specific legal situations\n\n"
                "TONE AND STYLE:\n"
                "- Professional and objective\n"
                "- Clear and accessible while maintaining legal accuracy\n"
                "- Respectful and neutral\n"
                "- Direct and practical, avoiding unnecessary legal jargon unless required for precision"
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
                user_question, self.model, optimized_context, file_references
            )
            
            if not anthropic_response.success:
                return AIChatResult(
                    success=False,
                    error=f"Anthropic API error: {anthropic_response.error}"
                )
            
            # Generate chat name based on user question
            chat_name = self.generate_chat_name(user_question.strip(), self.model)
            
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

    def _get_anthropic_response(self, user_question: str, model: str = "claude-3-haiku-20240307",
                               conversation_context: str = None, file_references: list = None) -> AnthropicResponse:
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
            
            # Prepare the system prompt (sent via Claude "system" field)
            system_context = (
                "You are a specialized legal AI assistant designed to analyze legal documents and provide accurate "
                "legal information. Your purpose is to assist legal professionals and individuals seeking legal understanding.\n\n"

                "CORE PRINCIPLES:\n"
                "- Provide precise, legally accurate information based on established legal principles\n"
                "- Focus on objective legal analysis without offering specific legal advice or attorney-client relationships\n"
                "- Maintain professional, clear language appropriate for legal contexts\n"
                "- Cite relevant statutes, regulations, case law, or legal precedents when applicable\n"
                "- Acknowledge jurisdictional variations and limitations in your knowledge\n\n"

                "RESPONSE FORMAT:\n"
                "- Use plain text only (no markdown, bullet points, or special formatting)\n"
                "- Be concise yet comprehensive enough to address the legal query fully\n"
                "- Structure responses logically: key findings first, followed by supporting details\n"
                "- Use clear paragraph breaks for readability\n\n"

                "DOCUMENT ANALYSIS APPROACH:\n"
                "When analyzing legal documents, identify and explain:\n"
                "- Main legal purpose and document type\n"
                "- Key parties, roles, and their obligations\n"
                "- Critical terms, conditions, and requirements\n"
                "- Important dates, deadlines, and time-sensitive provisions\n"
                "- Legal rights, remedies, and liabilities\n"
                "- Potential legal risks, ambiguities, or areas requiring attention\n"
                "- Relevant jurisdictional law or governing provisions\n"
                "- Cross-references to related clauses or external legal requirements\n\n"

                "GENERAL LEGAL QUESTIONS:\n"
                "When answering legal questions:\n"
                "- Provide clear explanations of legal concepts and terminology\n"
                "- Reference applicable laws, regulations, or legal standards\n"
                "- Distinguish between general legal principles and jurisdiction-specific rules\n"
                "- Explain practical implications and typical legal outcomes\n"
                "- Identify when professional legal counsel should be consulted\n\n"

                "CRITICAL LIMITATIONS:\n"
                "- Always clarify that you do not provide legal advice or replace qualified legal counsel\n"
                "- State when information may be jurisdiction-dependent or time-sensitive\n"
                "- Acknowledge gaps in your knowledge or when updated legal research is needed\n"
                "- Never guarantee legal outcomes or suggest specific legal strategies for individual cases\n"
                "- Recommend consulting a licensed attorney for specific legal situations\n\n"

                "TONE AND STYLE:\n"
                "- Professional and objective\n"
                "- Clear and accessible while maintaining legal accuracy\n"
                "- Respectful and neutral\n"
                "- Direct and practical, avoiding unnecessary legal jargon unless required for precision"
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
            if file_references:
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


# Global instance
anthropic_chat_service = AnthropicChatService()
