"""
Tokenizer Service for Anthropic Claude

Production-ready token counting and context management service.
Handles token counting, context truncation, and intelligent message management.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from anthropic import Anthropic
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage statistics"""
    total_tokens: int
    context_tokens: int
    user_question_tokens: int
    file_references_tokens: int = 0
    system_prompt_tokens: int = 0


@dataclass
class ContextTruncationResult:
    """Result of context truncation"""
    truncated_context: str
    messages_included: int
    messages_skipped: int
    tokens_used: int
    tokens_saved: int


class AnthropicTokenizerService:
    """
    Production-ready tokenizer service for Anthropic Claude
    
    Features:
    - Accurate token counting using Anthropic's official client
    - Intelligent context truncation
    - Configurable token limits
    - Token usage tracking and optimization
    """
    
    def __init__(self):
        """Initialize the tokenizer service"""
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not configured - using fallback token estimation")
            self.client = None
        else:
            self.client = Anthropic(api_key=self.api_key)
        
        # Production-oriented token limits (env-overridable)
        self.max_context_tokens = int(os.getenv('ANTHROPIC_MAX_CONTEXT_TOKENS', '25000'))
        self.max_user_question_tokens = int(os.getenv('ANTHROPIC_MAX_USER_QUESTION_TOKENS', '5000'))
        self.max_document_tokens = int(os.getenv('ANTHROPIC_MAX_DOCUMENT_TOKENS', '50000'))
        self.max_output_tokens = int(os.getenv('ANTHROPIC_MAX_OUTPUT_TOKENS', '8000'))
        self.max_total_tokens = int(os.getenv('ANTHROPIC_MAX_TOTAL_TOKENS', '90000'))
        
        # Context management settings
        self.target_context_tokens = int(os.getenv('ANTHROPIC_TARGET_CONTEXT_TOKENS', '20000'))
        self.min_messages_to_keep = int(os.getenv('ANTHROPIC_MIN_MESSAGES_TO_KEEP', '2'))
        self.max_messages_to_keep = int(os.getenv('ANTHROPIC_MAX_MESSAGES_TO_KEEP', '15'))
        self.token_buffer = int(os.getenv('ANTHROPIC_TOKEN_BUFFER', '1000'))
        
        # Optional TikToken fallback for better local estimates
        try:
            import tiktoken  # type: ignore
            self.tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("TikToken loaded for fallback token counting")
        except Exception:
            self.tiktoken_encoding = None
            logger.warning("TikToken not available - using character-based estimation")
        
        logger.info(
            f"AnthropicTokenizerService initialized with limits: context={self.max_context_tokens}, "
            f"user_question={self.max_user_question_tokens}, document={self.max_document_tokens}, total={self.max_total_tokens}"
        )
    
    def count_tokens(self, text: str, model: str = None) -> int:
        """
        Count tokens in text using Anthropic's official client
        
        Args:
            text: Text to count tokens for
            model: Model to use for token counting (defaults to self.model)
            
        Returns:
            Number of tokens
        """
        try:
            if not text or not text.strip():
                return 0
            
            if not self.client:
                # Fallback chain: TikToken → char-based
                if hasattr(self, 'tiktoken_encoding') and self.tiktoken_encoding:
                    try:
                        return len(self.tiktoken_encoding.encode(text))
                    except Exception:
                        pass
                # Rough estimation (1 token ≈ 4 chars)
                return len(text) // 4
            
            model = model or "claude-sonnet-4-5-20250929"
            messages = [{"role": "user", "content": text}]
            
            response = self.client.messages.count_tokens(
                model=model,
                messages=messages
            )
            
            return response.input_tokens
        except Exception as e:
            logger.error(f"Error counting tokens: {str(e)}")
            # Fallback chain
            if hasattr(self, 'tiktoken_encoding') and self.tiktoken_encoding:
                try:
                    return len(self.tiktoken_encoding.encode(text))
                except Exception:
                    pass
            return len(text) // 4
    
    def count_tokens_in_messages(self, messages: List[Dict[str, Any]], model: str = None) -> int:
        """
        Count tokens in a list of messages using Anthropic's official API
        
        Args:
            messages: List of message dictionaries
            model: Model to use for token counting
            
        Returns:
            Total token count
        """
        try:
            if not messages:
                return 0
            
            if not self.client:
                # Fallback: sum individual token counts
                total_tokens = 0
                for message in messages:
                    if isinstance(message, dict):
                        content = message.get('content', '')
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    total_tokens += self.count_tokens(item.get('text', ''))
                        else:
                            total_tokens += self.count_tokens(str(content))
                    else:
                        total_tokens += self.count_tokens(str(message))
                return total_tokens
            
            model = model or "claude-sonnet-4-5-20250929"
            
            # Convert messages to Anthropic format
            anthropic_messages = []
            for message in messages:
                if isinstance(message, dict):
                    role = message.get('role', 'user')
                    content = message.get('content', '')
                    
                    # Handle different content types
                    if isinstance(content, list):
                        # Structured content (e.g., with file references)
                        anthropic_messages.append({
                            "role": role,
                            "content": content
                        })
                    else:
                        # Simple text content
                        anthropic_messages.append({
                            "role": role,
                            "content": str(content)
                        })
            
            response = self.client.messages.count_tokens(
                model=model,
                messages=anthropic_messages
            )
            
            return response.input_tokens
        except Exception as e:
            logger.error(f"Error counting tokens in messages: {str(e)}")
            # Fallback: sum individual token counts
            total_tokens = 0
            for message in messages:
                if isinstance(message, dict):
                    content = message.get('content', '')
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                total_tokens += self.count_tokens(item.get('text', ''))
                    else:
                        total_tokens += self.count_tokens(str(content))
                else:
                    total_tokens += self.count_tokens(str(message))
            return total_tokens
    
    def estimate_file_reference_tokens(self, file_references: List[Any]) -> int:
        """
        Estimate tokens for file references
        
        Args:
            file_references: List of file IDs or detail dicts
            
        Returns:
            Estimated token count
        """
        if not file_references:
            return 0
        
        total_tokens = 0
        for ref in file_references:
            if isinstance(ref, dict):
                total_tokens += 50  # base structure overhead
                # Prefer explicit estimate if provided
                est = ref.get('estimated_tokens')
                if isinstance(est, int) and est > 0:
                    total_tokens += est
                elif 'size_bytes' in ref and isinstance(ref.get('size_bytes'), int):
                    # Rough estimate for text: ~1 token per 4 bytes
                    total_tokens += max(0, ref['size_bytes'] // 4)
                else:
                    # Conservative default for unknown sizes
                    total_tokens += 5000
            else:
                # Simple file id
                total_tokens += 50
        return total_tokens
    
    def calculate_token_usage(self, user_question: str, context: str = None, 
                            file_references: List[Any] = None, model: str = None,
                            system_prompt: Optional[str] = None) -> TokenUsage:
        """
        Calculate comprehensive token usage using Anthropic's official API
        
        Args:
            user_question: User's question
            context: Previous conversation context
            file_references: List of file IDs
            model: Model to use for token counting
            
        Returns:
            TokenUsage object with detailed breakdown
        """
        model = model or "claude-sonnet-4-5-20250929"
        
        # Build the complete message structure
        messages = []
        
        # Add context as previous messages if provided
        if context and context.strip():
            context_messages = self._parse_context_messages(context)
            messages.extend(context_messages)
        
        # Add current user question (without file references for token counting)
        # File references are handled separately as they don't count towards input tokens
        messages.append({
            "role": "user",
            "content": user_question
        })
        
        # System prompt for counting (match actual request prompt when provided)
        TOKEN_COUNTING_SYSTEM_PROMPT = system_prompt or (
            "You are a token counting assistant. This is a system message used only for "
            "accurate token calculation and will not generate any response."
        )
        
        try:
            if not self.client:
                # Fallback to individual counting
                user_question_tokens = self.count_tokens(user_question, model)
                context_tokens = self.count_tokens(context, model) if context else 0
                file_references_tokens = self.estimate_file_reference_tokens(file_references)
                system_prompt_tokens = self.count_tokens(TOKEN_COUNTING_SYSTEM_PROMPT, model)
                
                total_tokens = (user_question_tokens + context_tokens + 
                               file_references_tokens + system_prompt_tokens)
                
                return TokenUsage(
                    total_tokens=total_tokens,
                    context_tokens=context_tokens,
                    user_question_tokens=user_question_tokens,
                    file_references_tokens=file_references_tokens,
                    system_prompt_tokens=system_prompt_tokens
                )
            
            # Use Anthropic's official token counting API
            response = self.client.messages.count_tokens(
                model=model,
                system=TOKEN_COUNTING_SYSTEM_PROMPT,
                messages=messages
            )
            
            total_tokens = response.input_tokens
            system_prompt_tokens = self.count_tokens(TOKEN_COUNTING_SYSTEM_PROMPT, model)
            user_question_tokens = self.count_tokens(user_question, model)
            context_tokens = self.count_tokens(context, model) if context else 0
            file_references_tokens = self.estimate_file_reference_tokens(file_references)
            
            return TokenUsage(
                total_tokens=total_tokens,
                context_tokens=context_tokens,
                user_question_tokens=user_question_tokens,
                file_references_tokens=file_references_tokens,
                system_prompt_tokens=system_prompt_tokens
            )
            
        except Exception as e:
            logger.error(f"Error calculating token usage with API: {str(e)}")
            # Fallback to individual counting
            user_question_tokens = self.count_tokens(user_question, model)
            context_tokens = self.count_tokens(context, model) if context else 0
            file_references_tokens = self.estimate_file_reference_tokens(file_references)
            # Fallback estimate for system prompt
            system_prompt_tokens = self.count_tokens(TOKEN_COUNTING_SYSTEM_PROMPT, model)
            
            total_tokens = (user_question_tokens + context_tokens + 
                           file_references_tokens + system_prompt_tokens)
            
            return TokenUsage(
                total_tokens=total_tokens,
                context_tokens=context_tokens,
                user_question_tokens=user_question_tokens,
                file_references_tokens=file_references_tokens,
                system_prompt_tokens=system_prompt_tokens
            )
    
    def truncate_context(self, context: str, target_tokens: int = None) -> ContextTruncationResult:
        """
        Intelligently truncate context to fit within token limits
        
        Args:
            context: Full conversation context
            target_tokens: Target token count (defaults to self.target_context_tokens)
            
        Returns:
            ContextTruncationResult with truncation details
        """
        if not context or not context.strip():
            return ContextTruncationResult(
                truncated_context="",
                messages_included=0,
                messages_skipped=0,
                tokens_used=0,
                tokens_saved=0
            )
        
        target_tokens = target_tokens or self.target_context_tokens
        original_tokens = self.count_tokens(context)
        
        if original_tokens <= target_tokens:
            return ContextTruncationResult(
                truncated_context=context,
                messages_included=self._count_messages_in_context(context),
                messages_skipped=0,
                tokens_used=original_tokens,
                tokens_saved=0
            )
        
        # Split context into messages and truncate intelligently
        messages = self._parse_context_messages(context)
        truncated_messages = self._truncate_messages_intelligently(messages, target_tokens)
        
        truncated_context = self._reconstruct_context(truncated_messages)
        final_tokens = self.count_tokens(truncated_context)
        
        return ContextTruncationResult(
            truncated_context=truncated_context,
            messages_included=len(truncated_messages),
            messages_skipped=len(messages) - len(truncated_messages),
            tokens_used=final_tokens,
            tokens_saved=original_tokens - final_tokens
        )
    
    def _count_messages_in_context(self, context: str) -> int:
        """Count the number of messages in context"""
        if not context:
            return 0
        
        # Count "Human:" and "Assistant:" occurrences
        human_count = context.count("Human:")
        assistant_count = context.count("Assistant:")
        return max(human_count, assistant_count)
    
    def _parse_context_messages(self, context: str) -> List[Dict[str, str]]:
        """Parse context into individual messages - supports multiple formats"""
        if not context or not context.strip():
            return []
        # JSON array of messages
        if context.lstrip().startswith('['):
            try:
                import json
                arr = json.loads(context)
                if isinstance(arr, list):
                    out = []
                    for m in arr:
                        if isinstance(m, dict):
                            role = m.get('role', 'user')
                            content = m.get('content', '')
                            out.append({'role': role, 'content': content})
                    return out
            except Exception:
                pass
        # Human:/Assistant: format
        messages = []
        lines = context.split('\n')
        current_message = None
        for line in lines:
            line = line.strip()
            if line.startswith("Human:"):
                if current_message:
                    messages.append(current_message)
                current_message = {"role": "user", "content": line[6:].strip()}
            elif line.startswith("Assistant:"):
                if current_message:
                    messages.append(current_message)
                current_message = {"role": "assistant", "content": line[10:].strip()}
            elif current_message and line:
                current_message["content"] += " " + line
        if current_message:
            messages.append(current_message)
        return messages
    
    def _truncate_messages_intelligently(self, messages: List[Dict[str, str]], 
                                       target_tokens: int) -> List[Dict[str, str]]:
        """Intelligently truncate messages to fit token limit"""
        if not messages:
            return []
        
        # Always keep the most recent messages
        messages_to_keep = []
        current_tokens = 0
        
        # Start from the end (most recent messages)
        for message in reversed(messages):
            message_tokens = self.count_tokens(message["content"])
            
            # Check if adding this message would exceed the limit
            if current_tokens + message_tokens > target_tokens:
                break
            
            messages_to_keep.insert(0, message)  # Insert at beginning to maintain order
            current_tokens += message_tokens
            
            # Ensure we keep at least minimum messages
            if len(messages_to_keep) >= self.min_messages_to_keep:
                # If we have enough messages and are close to target, stop
                if current_tokens >= target_tokens * 0.8:
                    break
        
        # Ensure we don't exceed maximum messages
        if len(messages_to_keep) > self.max_messages_to_keep:
            messages_to_keep = messages_to_keep[-self.max_messages_to_keep:]
        
        return messages_to_keep
    
    def _reconstruct_context(self, messages: List[Dict[str, str]]) -> str:
        """Reconstruct context from truncated messages"""
        if not messages:
            return ""
        
        context_parts = []
        for message in messages:
            if message["role"] == "human":
                context_parts.append(f"Human: {message['content']}")
            elif message["role"] == "assistant":
                context_parts.append(f"Assistant: {message['content']}")
        
        return "\n\n".join(context_parts)
    
    def validate_token_limits(self, user_question: str, context: str = None, 
                            file_references: List[Any] = None,
                            system_prompt: Optional[str] = None) -> Tuple[bool, str, TokenUsage]:
        """
        Validate if the request fits within token limits
        
        Args:
            user_question: User's question
            context: Previous conversation context
            file_references: List of file IDs
            
        Returns:
            Tuple of (is_valid, error_message, token_usage)
        """
        token_usage = self.calculate_token_usage(user_question, context, file_references, system_prompt=system_prompt)
        
        # Check individual limits
        if token_usage.user_question_tokens > self.max_user_question_tokens:
            return False, f"User question too long: {token_usage.user_question_tokens} tokens (max: {self.max_user_question_tokens})", token_usage
        
        if token_usage.context_tokens > self.max_context_tokens:
            return False, f"Context too long: {token_usage.context_tokens} tokens (max: {self.max_context_tokens})", token_usage
        
        if token_usage.total_tokens > self.max_total_tokens:
            return False, f"Total tokens exceed limit: {token_usage.total_tokens} tokens (max: {self.max_total_tokens})", token_usage
        
        return True, "", token_usage
    
    def optimize_context_for_request(self, user_question: str, context: str = None, 
                                   file_references: List[Any] = None, model: str = None,
                                   system_prompt: Optional[str] = None) -> Tuple[str, TokenUsage, ContextTruncationResult]:
        """
        Optimize context to fit within token limits while preserving important information
        
        Args:
            user_question: User's question
            context: Previous conversation context
            file_references: List of file IDs
            
        Returns:
            Tuple of (optimized_context, token_usage, truncation_result)
        """
        # Calculate initial token usage
        token_usage = self.calculate_token_usage(user_question, context, file_references, model, system_prompt)
        
        # If within limits, return as-is
        if token_usage.total_tokens <= self.max_total_tokens:
            return context or "", token_usage, ContextTruncationResult(
                truncated_context=context or "",
                messages_included=self._count_messages_in_context(context or ""),
                messages_skipped=0,
                tokens_used=token_usage.context_tokens,
                tokens_saved=0
            )
        
        # Calculate how many tokens we need to save
        tokens_to_save = token_usage.total_tokens - self.max_total_tokens
        target_context_tokens = max(0, token_usage.context_tokens - tokens_to_save)
        
        # Truncate context
        truncation_result = self.truncate_context(context or "", target_context_tokens)
        
        # Recalculate token usage with truncated context
        optimized_token_usage = self.calculate_token_usage(
            user_question, 
            truncation_result.truncated_context, 
            file_references,
            model,
            system_prompt
        )
        
        logger.info(f"Context optimized: {truncation_result.messages_skipped} messages skipped, "
                   f"{truncation_result.tokens_saved} tokens saved")
        
        return truncation_result.truncated_context, optimized_token_usage, truncation_result
    
    def get_token_statistics(self) -> Dict[str, Any]:
        """Get current token configuration and statistics"""
        return {
            "limits": {
                "max_context_tokens": self.max_context_tokens,
                "max_user_question_tokens": self.max_user_question_tokens,
                "max_document_tokens": getattr(self, 'max_document_tokens', None),
                "max_output_tokens": getattr(self, 'max_output_tokens', None),
                "max_total_tokens": self.max_total_tokens,
                "target_context_tokens": self.target_context_tokens,
                "token_buffer": getattr(self, 'token_buffer', None)
            },
            "context_management": {
                "min_messages_to_keep": self.min_messages_to_keep,
                "max_messages_to_keep": self.max_messages_to_keep
            }
        }

    # Additional helpers
    def validate_document_tokens(self, document_content: str, document_name: str = "Document") -> Tuple[bool, str, int]:
        token_count = self.count_tokens(document_content)
        if hasattr(self, 'max_document_tokens') and token_count > self.max_document_tokens:
            return (
                False,
                f"{document_name} too large: {token_count:,} tokens (max: {self.max_document_tokens:,})",
                token_count,
            )
        # warning log if >85%
        try:
            warning_threshold = int(self.max_document_tokens * 0.85)
            if token_count > warning_threshold:
                logger.warning(
                    f"{document_name} is large: {token_count:,} tokens "
                    f"({(token_count/self.max_document_tokens)*100:.1f}% of limit)"
                )
        except Exception:
            pass
        return True, "", token_count

    def estimate_cost(self, token_usage: TokenUsage, estimated_output_tokens: Optional[int] = None) -> Dict[str, Any]:
        estimated_output_tokens = estimated_output_tokens or getattr(self, 'max_output_tokens', 0) or 0
        # Example pricing; adjust as needed
        INPUT_COST_PER_MILLION = 3.00
        OUTPUT_COST_PER_MILLION = 15.00
        input_cost = (token_usage.total_tokens / 1_000_000) * INPUT_COST_PER_MILLION
        output_cost = (estimated_output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION
        total_cost = input_cost + output_cost
        return {
            "input_tokens": token_usage.total_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6),
            "formatted": {
                "input": f"${input_cost:.6f}",
                "output": f"${output_cost:.6f}",
                "total": f"${total_cost:.6f}",
            },
        }


# Global instance
tokenizer_service = AnthropicTokenizerService()
