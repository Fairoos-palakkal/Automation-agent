"""Plan and Task models — Phase 2.1.

Plan is the structured output of the Planner agent: a list of Tasks,
each assigned to exactly one Agent type, with its own budget.

Neither Plan nor Task has any LLM dependency — they are pure Pydantic models.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class AgentType(str, Enum):
    BROWSER = "browser"
    API = "api"


class TaskBudget(BaseModel):
    """Typed resource limits for a Task with positive integers."""

    max_actions: int = Field(default=20, ge=0)
    max_tokens: int = Field(default=50000, ge=0)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# Alias for compatibility with audit and docs
Budget = TaskBudget


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
    budget: TaskBudget = Field(default_factory=TaskBudget)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    """A structured list of Tasks produced by the Planner for one Run.

    Attributes:
        objective: The original Objective this Plan is addressing.
        tasks: Ordered list of Tasks to execute (1 to 6 tasks, unique IDs).
        metadata: Optional trace/versioning metadata.
    """

    objective: str
    tasks: List[Task] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, tasks: List[Task]) -> List[Task]:
        if not tasks:
            raise ValueError("Plan must contain at least 1 task (cannot be empty)")
        if len(tasks) > 6:
            raise ValueError("Plan cannot contain more than 6 tasks")
        ids = [t.id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Task IDs must be unique within a plan")
        return tasks

