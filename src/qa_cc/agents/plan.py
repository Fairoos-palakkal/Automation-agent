"""Plan and Task models — Phase 2.1.

Plan is the structured output of the Planner agent: a list of Tasks,
each assigned to exactly one Agent type, with its own budget.

Neither Plan nor Task has any LLM dependency — they are pure Pydantic models.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    BROWSER = "browser"
    API = "api"


class Task(BaseModel):
    """One unit of work in a Plan.

    Attributes:
        id: Unique identifier for this task within the Plan.
        goal: Natural-language description of what this Task must accomplish.
        assignee: Which Agent type will execute this Task (browser or api).
        budget: Resource limits for this Task (max_actions, max_tokens).
        metadata: Optional additional context for the executing agent.
    """

    id: str
    goal: str
    assignee: AgentType
    budget: Dict[str, Any] = Field(...)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """A structured list of Tasks produced by the Planner for one Run.

    Attributes:
        objective: The original Objective this Plan is addressing.
        tasks: Ordered list of Tasks to execute.
        metadata: Optional trace/versioning metadata.
    """

    objective: str
    tasks: List[Task] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
