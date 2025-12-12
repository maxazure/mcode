"""Todo tool for task tracking and management during conversations"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
from pathlib import Path

from .base import BaseTool, ToolParameter, ToolResult

if TYPE_CHECKING:
    pass


class TodoStatus(str, Enum):
    """Todo item status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    """Todo item priority"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class TodoItem:
    """A single todo item with optional technical details"""

    id: str
    content: str
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: Optional[str] = None
    # Technical details for Plan-Execute workflow
    file_path: Optional[str] = None  # Target file for this task
    details: Optional[str] = None  # Technical implementation details

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
            "file_path": self.file_path,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoItem":
        """Create from dictionary"""
        return cls(
            id=data["id"],
            content=data["content"],
            status=TodoStatus(data.get("status", "pending")),
            priority=TodoPriority(data.get("priority", "medium")),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
            notes=data.get("notes"),
            file_path=data.get("file_path"),
            details=data.get("details"),
        )


class TodoList:
    """Manages a list of todo items"""

    def __init__(self) -> None:
        self._items: dict[str, TodoItem] = {}
        self._counter = 0

    def add(
        self,
        content: str,
        priority: TodoPriority = TodoPriority.MEDIUM,
        item_id: Optional[str] = None,
    ) -> TodoItem:
        """Add a new todo item"""
        if item_id is None:
            self._counter += 1
            item_id = str(self._counter)

        item = TodoItem(
            id=item_id,
            content=content,
            priority=priority,
        )
        self._items[item_id] = item
        return item

    def get(self, item_id: str) -> Optional[TodoItem]:
        """Get a todo item by ID"""
        return self._items.get(item_id)

    def update_status(
        self,
        item_id: str,
        status: TodoStatus,
    ) -> Optional[TodoItem]:
        """Update the status of a todo item"""
        item = self._items.get(item_id)
        if item:
            item.status = status
            item.updated_at = datetime.now().isoformat()
            if status == TodoStatus.COMPLETED:
                item.completed_at = datetime.now().isoformat()
        return item

    def update_content(
        self,
        item_id: str,
        content: str,
    ) -> Optional[TodoItem]:
        """Update the content of a todo item"""
        item = self._items.get(item_id)
        if item:
            item.content = content
            item.updated_at = datetime.now().isoformat()
        return item

    def update_priority(
        self,
        item_id: str,
        priority: TodoPriority,
    ) -> Optional[TodoItem]:
        """Update the priority of a todo item"""
        item = self._items.get(item_id)
        if item:
            item.priority = priority
            item.updated_at = datetime.now().isoformat()
        return item

    def add_note(
        self,
        item_id: str,
        note: str,
    ) -> Optional[TodoItem]:
        """Add a note to a todo item"""
        item = self._items.get(item_id)
        if item:
            if item.notes:
                item.notes = f"{item.notes}\n{note}"
            else:
                item.notes = note
            item.updated_at = datetime.now().isoformat()
        return item

    def remove(self, item_id: str) -> bool:
        """Remove a todo item"""
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def list_all(self) -> list[TodoItem]:
        """List all todo items"""
        return list(self._items.values())

    def list_by_status(self, status: TodoStatus) -> list[TodoItem]:
        """List items by status"""
        return [item for item in self._items.values() if item.status == status]

    def list_by_priority(self, priority: TodoPriority) -> list[TodoItem]:
        """List items by priority"""
        return [item for item in self._items.values() if item.priority == priority]

    def clear_completed(self) -> int:
        """Remove all completed items"""
        completed = [k for k, v in self._items.items() if v.status == TodoStatus.COMPLETED]
        for k in completed:
            del self._items[k]
        return len(completed)

    def to_dict(self) -> dict[str, Any]:
        """Convert entire list to dictionary"""
        return {
            "items": [item.to_dict() for item in self._items.values()],
            "counter": self._counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoList":
        """Create from dictionary"""
        todo_list = cls()
        todo_list._counter = data.get("counter", 0)
        for item_data in data.get("items", []):
            item = TodoItem.from_dict(item_data)
            todo_list._items[item.id] = item
        return todo_list

    def format_markdown(self) -> str:
        """Format as markdown"""
        lines = ["# Todo List\n"]

        # Group by status
        in_progress = self.list_by_status(TodoStatus.IN_PROGRESS)
        pending = self.list_by_status(TodoStatus.PENDING)
        completed = self.list_by_status(TodoStatus.COMPLETED)

        if in_progress:
            lines.append("## 🔄 In Progress")
            for item in in_progress:
                priority_marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    item.priority.value, ""
                )
                lines.append(f"- [ ] {priority_marker} **{item.id}**: {item.content}")
            lines.append("")

        if pending:
            lines.append("## 📋 Pending")
            for item in pending:
                priority_marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    item.priority.value, ""
                )
                lines.append(f"- [ ] {priority_marker} **{item.id}**: {item.content}")
            lines.append("")

        if completed:
            lines.append("## ✅ Completed")
            for item in completed:
                lines.append(f"- [x] **{item.id}**: {item.content}")
            lines.append("")

        return "\n".join(lines)


# Global todo list instance (persists across tool calls in a session)
_global_todo_list: Optional[TodoList] = None


def get_todo_list() -> TodoList:
    """Get global todo list"""
    global _global_todo_list
    if _global_todo_list is None:
        _global_todo_list = TodoList()
    return _global_todo_list


def reset_todo_list() -> None:
    """Reset global todo list"""
    global _global_todo_list
    _global_todo_list = TodoList()


class TodoWriteTool(BaseTool):
    """Create and manage a structured task list for the current session

    Use this tool to track progress, organize complex tasks, and demonstrate
    thoroughness. Helps the user understand the progress of their requests.
    """

    name = "todowrite"
    description = """Create and manage a structured task list for your current coding session.

Use this tool when:
1. Complex multi-step tasks - Tasks requiring 3+ distinct steps
2. User provides multiple tasks - Numbered or comma-separated lists
3. After receiving new instructions - Capture requirements as todos
4. After completing a task - Mark it complete and add follow-up tasks

When NOT to use:
- Single, straightforward tasks
- Trivial tasks under 3 steps
- Purely conversational requests

Task States:
- pending: Not yet started
- in_progress: Currently working on (limit to ONE at a time)
- completed: Finished successfully
- cancelled: No longer needed"""

    parameters = [
        ToolParameter(
            name="todos",
            type="array",
            description="Array of todo items to write with optional technical details",
            items={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique identifier for the todo item"},
                    "content": {"type": "string", "description": "Brief description of the task"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Current status of the task",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority level of the task",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Target file path for this task (optional)",
                    },
                    "details": {
                        "type": "string",
                        "description": "Technical implementation details (optional)",
                    },
                },
                "required": ["id", "content", "status", "priority"],
            },
        ),
    ]
    risk_level = "low"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Write/update the todo list"""
        todos = kwargs.get("todos", [])

        if not todos:
            return ToolResult(
                success=False,
                output="",
                error="No todos provided",
            )

        try:
            todo_list = get_todo_list()

            # Process each todo item
            updated_items = []
            for todo_data in todos:
                item_id = str(todo_data.get("id", ""))
                content = todo_data.get("content", "")
                status_str = todo_data.get("status", "pending")
                priority_str = todo_data.get("priority", "medium")
                file_path = todo_data.get("file_path")
                details = todo_data.get("details")

                # Parse status and priority
                try:
                    status = TodoStatus(status_str)
                except ValueError:
                    status = TodoStatus.PENDING

                try:
                    priority = TodoPriority(priority_str)
                except ValueError:
                    priority = TodoPriority.MEDIUM

                # Check if item exists
                existing = todo_list.get(item_id)

                if existing:
                    # Update existing item
                    if content and content != existing.content:
                        todo_list.update_content(item_id, content)
                    if status != existing.status:
                        todo_list.update_status(item_id, status)
                    if priority != existing.priority:
                        todo_list.update_priority(item_id, priority)
                    # Update file_path and details if provided
                    item = todo_list.get(item_id)
                    if file_path is not None:
                        item.file_path = file_path
                    if details is not None:
                        item.details = details
                    updated_items.append(item)
                else:
                    # Add new item
                    item = todo_list.add(content, priority, item_id)
                    item.file_path = file_path
                    item.details = details
                    if status != TodoStatus.PENDING:
                        todo_list.update_status(item_id, status)
                    updated_items.append(item)

            # Format output
            output_lines = ["Todo list updated:\n"]
            for item in updated_items:
                status_icon = {
                    TodoStatus.PENDING: "⏳",
                    TodoStatus.IN_PROGRESS: "🔄",
                    TodoStatus.COMPLETED: "✅",
                    TodoStatus.CANCELLED: "❌",
                }.get(item.status, "")
                line = f"{status_icon} [{item.id}] {item.content} ({item.priority.value})"
                if item.file_path:
                    line += f" -> {item.file_path}"
                output_lines.append(line)
                if item.details:
                    output_lines.append(f"    Details: {item.details}")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={
                    "items_count": len(updated_items),
                    "todos": [item.to_dict() for item in updated_items],
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to update todos: {str(e)}",
            )


class TodoReadTool(BaseTool):
    """Read the current todo list"""

    name = "todoread"
    description = """Read the current todo list to see all tasks and their status.

Returns the full todo list including:
- All items with their status (pending, in_progress, completed, cancelled)
- Priority levels (high, medium, low)
- Creation and update times"""

    parameters = [
        ToolParameter(
            name="status",
            type="string",
            description="Filter by status (pending, in_progress, completed, cancelled)",
            required=False,
            enum=["pending", "in_progress", "completed", "cancelled"],
        ),
        ToolParameter(
            name="format",
            type="string",
            description="Output format (text, markdown, json)",
            required=False,
            default="text",
            enum=["text", "markdown", "json"],
        ),
    ]
    risk_level = "low"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Read the todo list"""
        status_filter = kwargs.get("status")
        output_format = kwargs.get("format", "text")

        try:
            todo_list = get_todo_list()

            # Get items based on filter
            if status_filter:
                try:
                    status = TodoStatus(status_filter)
                    items = todo_list.list_by_status(status)
                except ValueError:
                    items = todo_list.list_all()
            else:
                items = todo_list.list_all()

            if not items:
                return ToolResult(
                    success=True,
                    output="Todo list is empty.",
                    metadata={"items_count": 0},
                )

            # Format output
            if output_format == "json":
                output = json.dumps([item.to_dict() for item in items], indent=2)
            elif output_format == "markdown":
                output = todo_list.format_markdown()
            else:
                # Text format
                lines = ["Current Todo List:", ""]

                # Group by status
                by_status = {}
                for item in items:
                    status_key = item.status.value
                    if status_key not in by_status:
                        by_status[status_key] = []
                    by_status[status_key].append(item)

                status_labels = {
                    "in_progress": "🔄 In Progress",
                    "pending": "📋 Pending",
                    "completed": "✅ Completed",
                    "cancelled": "❌ Cancelled",
                }

                for status_key in ["in_progress", "pending", "completed", "cancelled"]:
                    if status_key in by_status:
                        lines.append(status_labels[status_key])
                        for item in by_status[status_key]:
                            priority_marker = {"high": "[H]", "medium": "[M]", "low": "[L]"}.get(
                                item.priority.value, ""
                            )
                            lines.append(f"  {priority_marker} {item.id}: {item.content}")
                        lines.append("")

                output = "\n".join(lines)

            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "items_count": len(items),
                    "by_status": {
                        s.value: len([i for i in items if i.status == s]) for s in TodoStatus
                    },
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to read todos: {str(e)}",
            )


class TodoClearTool(BaseTool):
    """Clear completed todos or reset the entire list"""

    name = "todoclear"
    description = """Clear completed todos from the list or reset the entire todo list.

Use this to clean up after completing a set of tasks."""

    parameters = [
        ToolParameter(
            name="mode",
            type="string",
            description="clear_completed (remove done items) or reset_all (clear everything)",
            required=False,
            default="clear_completed",
            enum=["clear_completed", "reset_all"],
        ),
    ]
    risk_level = "low"

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Clear todos"""
        mode = kwargs.get("mode", "clear_completed")

        try:
            if mode == "reset_all":
                reset_todo_list()
                return ToolResult(
                    success=True,
                    output="Todo list has been reset.",
                    metadata={"cleared_count": 0, "mode": "reset_all"},
                )
            else:
                todo_list = get_todo_list()
                cleared = todo_list.clear_completed()
                return ToolResult(
                    success=True,
                    output=f"Cleared {cleared} completed todo(s).",
                    metadata={"cleared_count": cleared, "mode": "clear_completed"},
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to clear todos: {str(e)}",
            )
