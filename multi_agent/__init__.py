"""
SQL Genie — Multi-Agent NL2SQL System
=====================================

A Supervisor/Orchestrator multi-agent architecture. Each agent is an
independent specialist with its own focused system prompt and LLM context.
The Supervisor owns shared AgentState and routes work between agents,
running a real Critic <-> Fixer correction loop with iteration limits.

Agents (see multi_agent/agents/):
  - GuardrailAgent    : blocks destructive / write intent
  - GeneratorAgent    : natural language -> SQL
  - CriticAgent       : validates SQL (dry-run + semantic audit)
  - FixerAgent        : repairs invalid SQL from critic feedback
  - FormatterAgent    : SQL results -> conversational answer

Pattern: Supervisor / Orchestrator (see multi-agent-patterns skill).

This package re-exports the public API so existing imports
(e.g. `from multi_agent import Supervisor`) keep working.
"""

from .state import (
    AgentState,
    clean_sql,
    _extract_json,
    _truthy,
    _summarize_results,
    _last_log,
)
from .base_agent import BaseAgent
from .agents import (
    GuardrailAgent,
    GeneratorAgent,
    ExplainerAgent,
    CriticAgent,
    FixerAgent,
    FormatterAgent,
    Supervisor,
)

__all__ = [
    "AgentState",
    "BaseAgent",
    "GuardrailAgent",
    "GeneratorAgent",
    "ExplainerAgent",
    "CriticAgent",
    "FixerAgent",
    "FormatterAgent",
    "Supervisor",
    "clean_sql",
]
