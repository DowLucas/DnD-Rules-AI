"""
Prompts package for the D&D rules assistant.
"""

from .agent_instructions import get_agent_instructions
from .insight_prompts import get_regular_insight_prompt, get_forced_insight_prompt
from .rules_question_prompt import get_rules_question_prompt

__all__ = [
    'get_agent_instructions',
    'get_regular_insight_prompt',
    'get_forced_insight_prompt',
    'get_rules_question_prompt',
] 