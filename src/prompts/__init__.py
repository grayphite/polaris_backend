"""
Prompts Module for POLARIS Backend
Centralized system prompts for different AI services
"""

from .adaptive_system_prompt import (
    get_adaptive_system_prompt,
    detect_question_type,
    get_tax_agent_rag_configuration
)

__all__ = [
    'get_adaptive_system_prompt',
    'detect_question_type',
    'get_tax_agent_rag_configuration'
]
