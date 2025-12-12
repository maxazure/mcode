"""E2E tests for Todo tools functionality"""

import pytest
import asyncio
from datetime import datetime

from maxagent.tools.todo import (
    TodoItem,
    TodoList,
    TodoStatus,
    TodoPriority,
    TodoWriteTool,
    TodoReadTool,
    TodoClearTool,
    get_todo_list,
    reset_todo_list,
)


# ========== Fixtures ==========


@pytest.fixture(autouse=True)
def clean_todo_list():
    """Reset the global todo list before each test"""
    reset_todo_list()
    yield
    reset_todo_list()


# ========== TodoItem Tests ==========


class TestTodoItem:
    """Test TodoItem dataclass"""

    def test_create_todo_item_defaults(self):
        """Test creating a TodoItem with default values"""
        item = TodoItem(id="1", content="Test task")

        assert item.id == "1"
        assert item.content == "Test task"
        assert item.status == TodoStatus.PENDING
        assert item.priority == TodoPriority.MEDIUM
        assert item.created_at is not None
        assert item.updated_at is None
        assert item.completed_at is None
        assert item.notes is None

    def test_create_todo_item_custom_values(self):
        """Test creating a TodoItem with custom values"""
        item = TodoItem(
            id="2",
            content="High priority task",
            status=TodoStatus.IN_PROGRESS,
            priority=TodoPriority.HIGH,
            notes="Some notes",
        )

        assert item.id == "2"
        assert item.content == "High priority task"
        assert item.status == TodoStatus.IN_PROGRESS
        assert item.priority == TodoPriority.HIGH
        assert item.notes == "Some notes"

    def test_todo_item_to_dict(self):
        """Test TodoItem.to_dict() method"""
        item = TodoItem(id="3", content="Dict test")
        data = item.to_dict()

        assert data["id"] == "3"
        assert data["content"] == "Dict test"
        assert data["status"] == "pending"
        assert data["priority"] == "medium"
        assert "created_at" in data

    def test_todo_item_from_dict(self):
        """Test TodoItem.from_dict() class method"""
        data = {
            "id": "4",
            "content": "From dict task",
            "status": "completed",
            "priority": "high",
            "notes": "Test note",
        }
        item = TodoItem.from_dict(data)

        assert item.id == "4"
        assert item.content == "From dict task"
        assert item.status == TodoStatus.COMPLETED
        assert item.priority == TodoPriority.HIGH
        assert item.notes == "Test note"

    def test_todo_item_from_dict_defaults(self):
        """Test TodoItem.from_dict() with minimal data"""
        data = {"id": "5", "content": "Minimal data"}
        item = TodoItem.from_dict(data)

        assert item.status == TodoStatus.PENDING
        assert item.priority == TodoPriority.MEDIUM


# ========== TodoList Tests ==========


class TestTodoList:
    """Test TodoList class"""

    def test_add_todo(self):
        """Test adding a todo item"""
        todo_list = TodoList()
        item = todo_list.add("Test task")

        assert item.id == "1"
        assert item.content == "Test task"
        assert item.status == TodoStatus.PENDING

    def test_add_multiple_todos(self):
        """Test adding multiple todo items"""
        todo_list = TodoList()
        item1 = todo_list.add("Task 1")
        item2 = todo_list.add("Task 2")
        item3 = todo_list.add("Task 3")

        assert item1.id == "1"
        assert item2.id == "2"
        assert item3.id == "3"
        assert len(todo_list.list_all()) == 3

    def test_add_with_custom_id(self):
        """Test adding a todo with custom ID"""
        todo_list = TodoList()
        item = todo_list.add("Custom ID task", item_id="custom-1")

        assert item.id == "custom-1"

    def test_add_with_priority(self):
        """Test adding a todo with custom priority"""
        todo_list = TodoList()
        item = todo_list.add("High priority", priority=TodoPriority.HIGH)

        assert item.priority == TodoPriority.HIGH

    def test_get_todo(self):
        """Test getting a todo by ID"""
        todo_list = TodoList()
        todo_list.add("Get test")

        item = todo_list.get("1")
        assert item is not None
        assert item.content == "Get test"

        # Non-existent ID
        assert todo_list.get("999") is None

    def test_update_status(self):
        """Test updating todo status"""
        todo_list = TodoList()
        todo_list.add("Status test")

        item = todo_list.update_status("1", TodoStatus.IN_PROGRESS)
        assert item is not None
        assert item.status == TodoStatus.IN_PROGRESS
        assert item.updated_at is not None

        item = todo_list.update_status("1", TodoStatus.COMPLETED)
        assert item is not None
        assert item.status == TodoStatus.COMPLETED
        assert item.completed_at is not None

    def test_update_content(self):
        """Test updating todo content"""
        todo_list = TodoList()
        todo_list.add("Original content")

        item = todo_list.update_content("1", "Updated content")
        assert item is not None
        assert item.content == "Updated content"
        assert item.updated_at is not None

    def test_update_priority(self):
        """Test updating todo priority"""
        todo_list = TodoList()
        todo_list.add("Priority test")

        item = todo_list.update_priority("1", TodoPriority.HIGH)
        assert item is not None
        assert item.priority == TodoPriority.HIGH
        assert item.updated_at is not None

    def test_add_note(self):
        """Test adding notes to a todo"""
        todo_list = TodoList()
        todo_list.add("Note test")

        item = todo_list.add_note("1", "First note")
        assert item is not None
        assert item.notes == "First note"

        item = todo_list.add_note("1", "Second note")
        assert item is not None
        assert item.notes is not None
        assert "First note" in item.notes
        assert "Second note" in item.notes

    def test_remove_todo(self):
        """Test removing a todo"""
        todo_list = TodoList()
        todo_list.add("Remove test")

        assert todo_list.remove("1") is True
        assert len(todo_list.list_all()) == 0

        # Non-existent ID
        assert todo_list.remove("999") is False

    def test_list_by_status(self):
        """Test listing todos by status"""
        todo_list = TodoList()
        todo_list.add("Pending 1")
        todo_list.add("Pending 2")
        item = todo_list.add("In progress")
        todo_list.update_status(item.id, TodoStatus.IN_PROGRESS)

        pending = todo_list.list_by_status(TodoStatus.PENDING)
        in_progress = todo_list.list_by_status(TodoStatus.IN_PROGRESS)

        assert len(pending) == 2
        assert len(in_progress) == 1

    def test_list_by_priority(self):
        """Test listing todos by priority"""
        todo_list = TodoList()
        todo_list.add("High 1", priority=TodoPriority.HIGH)
        todo_list.add("High 2", priority=TodoPriority.HIGH)
        todo_list.add("Low 1", priority=TodoPriority.LOW)

        high = todo_list.list_by_priority(TodoPriority.HIGH)
        low = todo_list.list_by_priority(TodoPriority.LOW)

        assert len(high) == 2
        assert len(low) == 1

    def test_clear_completed(self):
        """Test clearing completed todos"""
        todo_list = TodoList()
        todo_list.add("Task 1")
        todo_list.add("Task 2")
        todo_list.add("Task 3")

        todo_list.update_status("1", TodoStatus.COMPLETED)
        todo_list.update_status("2", TodoStatus.COMPLETED)

        cleared = todo_list.clear_completed()
        assert cleared == 2
        assert len(todo_list.list_all()) == 1

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization"""
        todo_list = TodoList()
        todo_list.add("Task 1")
        todo_list.add("Task 2", priority=TodoPriority.HIGH)
        todo_list.update_status("1", TodoStatus.COMPLETED)

        data = todo_list.to_dict()
        restored = TodoList.from_dict(data)

        assert len(restored.list_all()) == 2
        assert restored._counter == 2

    def test_format_markdown(self):
        """Test markdown formatting"""
        todo_list = TodoList()
        todo_list.add("In progress task")
        todo_list.add("Pending task")
        todo_list.add("Completed task")

        todo_list.update_status("1", TodoStatus.IN_PROGRESS)
        todo_list.update_status("3", TodoStatus.COMPLETED)

        md = todo_list.format_markdown()

        assert "# Todo List" in md
        assert "## 🔄 In Progress" in md
        assert "## 📋 Pending" in md
        assert "## ✅ Completed" in md


# ========== TodoWriteTool Tests ==========


class TestTodoWriteTool:
    """Test TodoWriteTool"""

    @pytest.mark.asyncio
    async def test_write_single_todo(self):
        """Test writing a single todo"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {
                    "id": "1",
                    "content": "Test task",
                    "status": "pending",
                    "priority": "high",
                }
            ]
        )

        assert result.success
        assert "Test task" in result.output
        assert result.metadata["items_count"] == 1

    @pytest.mark.asyncio
    async def test_write_multiple_todos(self):
        """Test writing multiple todos"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"id": "1", "content": "Task 1", "status": "pending", "priority": "high"},
                {"id": "2", "content": "Task 2", "status": "in_progress", "priority": "medium"},
                {"id": "3", "content": "Task 3", "status": "completed", "priority": "low"},
            ]
        )

        assert result.success
        assert result.metadata["items_count"] == 3

        # Verify in global list
        todo_list = get_todo_list()
        assert len(todo_list.list_all()) == 3

    @pytest.mark.asyncio
    async def test_update_existing_todo(self):
        """Test updating an existing todo"""
        tool = TodoWriteTool()

        # Create
        await tool.execute(
            todos=[{"id": "1", "content": "Original", "status": "pending", "priority": "medium"}]
        )

        # Update
        result = await tool.execute(
            todos=[{"id": "1", "content": "Updated", "status": "completed", "priority": "high"}]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert item.content == "Updated"
        assert item.status == TodoStatus.COMPLETED
        assert item.priority == TodoPriority.HIGH

    @pytest.mark.asyncio
    async def test_write_empty_todos(self):
        """Test writing empty todos list"""
        tool = TodoWriteTool()
        result = await tool.execute(todos=[])

        assert not result.success
        assert result.error == "No todos provided"

    @pytest.mark.asyncio
    async def test_write_invalid_priority(self):
        """Test writing todo with invalid priority defaults to medium"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {"id": "1", "content": "Test", "status": "pending", "priority": "invalid_priority"}
            ]
        )

        assert result.success
        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert item.priority == TodoPriority.MEDIUM


# ========== TodoReadTool Tests ==========


class TestTodoReadTool:
    """Test TodoReadTool"""

    @pytest.mark.asyncio
    async def test_read_empty_list(self):
        """Test reading empty todo list"""
        tool = TodoReadTool()
        result = await tool.execute()

        assert result.success
        assert "empty" in result.output.lower()
        assert result.metadata["items_count"] == 0

    @pytest.mark.asyncio
    async def test_read_with_todos(self):
        """Test reading todo list with items"""
        # Add some todos first
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[
                {"id": "1", "content": "Task 1", "status": "pending", "priority": "high"},
                {"id": "2", "content": "Task 2", "status": "in_progress", "priority": "medium"},
            ]
        )

        read_tool = TodoReadTool()
        result = await read_tool.execute()

        assert result.success
        assert result.metadata["items_count"] == 2

    @pytest.mark.asyncio
    async def test_read_with_status_filter(self):
        """Test reading todos filtered by status"""
        # Add todos with different statuses
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[
                {"id": "1", "content": "Pending", "status": "pending", "priority": "medium"},
                {
                    "id": "2",
                    "content": "In Progress",
                    "status": "in_progress",
                    "priority": "medium",
                },
                {"id": "3", "content": "Completed", "status": "completed", "priority": "medium"},
            ]
        )

        read_tool = TodoReadTool()

        # Filter pending
        result = await read_tool.execute(status="pending")
        assert result.success
        assert result.metadata["items_count"] == 1

        # Filter in_progress
        result = await read_tool.execute(status="in_progress")
        assert result.success
        assert result.metadata["items_count"] == 1

    @pytest.mark.asyncio
    async def test_read_text_format(self):
        """Test reading in text format"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[{"id": "1", "content": "Test", "status": "pending", "priority": "high"}]
        )

        read_tool = TodoReadTool()
        result = await read_tool.execute(format="text")

        assert result.success
        assert "Current Todo List" in result.output
        assert "[H]" in result.output  # High priority marker

    @pytest.mark.asyncio
    async def test_read_markdown_format(self):
        """Test reading in markdown format"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[{"id": "1", "content": "Test", "status": "pending", "priority": "medium"}]
        )

        read_tool = TodoReadTool()
        result = await read_tool.execute(format="markdown")

        assert result.success
        assert "# Todo List" in result.output

    @pytest.mark.asyncio
    async def test_read_json_format(self):
        """Test reading in JSON format"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[{"id": "1", "content": "Test", "status": "pending", "priority": "medium"}]
        )

        read_tool = TodoReadTool()
        result = await read_tool.execute(format="json")

        assert result.success
        import json

        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "1"


# ========== TodoClearTool Tests ==========


class TestTodoClearTool:
    """Test TodoClearTool"""

    @pytest.mark.asyncio
    async def test_clear_completed(self):
        """Test clearing completed todos"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[
                {"id": "1", "content": "Completed", "status": "completed", "priority": "medium"},
                {"id": "2", "content": "Pending", "status": "pending", "priority": "medium"},
                {
                    "id": "3",
                    "content": "Also Completed",
                    "status": "completed",
                    "priority": "medium",
                },
            ]
        )

        clear_tool = TodoClearTool()
        result = await clear_tool.execute(mode="clear_completed")

        assert result.success
        assert result.metadata["cleared_count"] == 2

        # Check remaining
        todo_list = get_todo_list()
        assert len(todo_list.list_all()) == 1

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """Test resetting entire todo list"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[
                {"id": "1", "content": "Task 1", "status": "pending", "priority": "medium"},
                {"id": "2", "content": "Task 2", "status": "in_progress", "priority": "medium"},
            ]
        )

        clear_tool = TodoClearTool()
        result = await clear_tool.execute(mode="reset_all")

        assert result.success
        assert result.metadata["mode"] == "reset_all"

        # Check list is empty
        todo_list = get_todo_list()
        assert len(todo_list.list_all()) == 0

    @pytest.mark.asyncio
    async def test_clear_with_no_completed(self):
        """Test clearing when there are no completed todos"""
        write_tool = TodoWriteTool()
        await write_tool.execute(
            todos=[
                {"id": "1", "content": "Pending", "status": "pending", "priority": "medium"},
            ]
        )

        clear_tool = TodoClearTool()
        result = await clear_tool.execute(mode="clear_completed")

        assert result.success
        assert result.metadata["cleared_count"] == 0


# ========== Global Functions Tests ==========


class TestGlobalFunctions:
    """Test global todo list functions"""

    def test_get_todo_list_singleton(self):
        """Test that get_todo_list returns the same instance"""
        list1 = get_todo_list()
        list2 = get_todo_list()

        assert list1 is list2

    def test_reset_todo_list(self):
        """Test resetting the global todo list"""
        todo_list = get_todo_list()
        todo_list.add("Test task")

        reset_todo_list()

        new_list = get_todo_list()
        assert len(new_list.list_all()) == 0


# ========== Integration Tests ==========


class TestTodoIntegration:
    """Integration tests for todo functionality"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test a complete todo workflow"""
        write_tool = TodoWriteTool()
        read_tool = TodoReadTool()
        clear_tool = TodoClearTool()

        # 1. Create tasks
        result = await write_tool.execute(
            todos=[
                {
                    "id": "task-1",
                    "content": "Research project",
                    "status": "pending",
                    "priority": "high",
                },
                {
                    "id": "task-2",
                    "content": "Write documentation",
                    "status": "pending",
                    "priority": "medium",
                },
                {"id": "task-3", "content": "Review code", "status": "pending", "priority": "low"},
            ]
        )
        assert result.success

        # 2. Start working on first task
        result = await write_tool.execute(
            todos=[
                {
                    "id": "task-1",
                    "content": "Research project",
                    "status": "in_progress",
                    "priority": "high",
                }
            ]
        )
        assert result.success

        # 3. Read current state
        result = await read_tool.execute()
        assert result.success
        assert result.metadata["by_status"]["in_progress"] == 1
        assert result.metadata["by_status"]["pending"] == 2

        # 4. Complete first task
        result = await write_tool.execute(
            todos=[
                {
                    "id": "task-1",
                    "content": "Research project",
                    "status": "completed",
                    "priority": "high",
                }
            ]
        )
        assert result.success

        # 5. Clear completed
        result = await clear_tool.execute(mode="clear_completed")
        assert result.success
        assert result.metadata["cleared_count"] == 1

        # 6. Verify remaining tasks
        result = await read_tool.execute()
        assert result.success
        assert result.metadata["items_count"] == 2

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent todo operations"""
        write_tool = TodoWriteTool()

        # Create multiple todos concurrently
        tasks = [
            write_tool.execute(
                todos=[
                    {
                        "id": f"t-{i}",
                        "content": f"Task {i}",
                        "status": "pending",
                        "priority": "medium",
                    }
                ]
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r.success for r in results)

        # Verify all items were added
        todo_list = get_todo_list()
        assert len(todo_list.list_all()) == 10


# ========== Edge Cases ==========


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self):
        """Test todo with special characters"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {
                    "id": "1",
                    "content": "Task with special chars: <>\"'&\n\ttab",
                    "status": "pending",
                    "priority": "medium",
                }
            ]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert "<>" in item.content

    @pytest.mark.asyncio
    async def test_unicode_content(self):
        """Test todo with unicode content"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {
                    "id": "1",
                    "content": "中文任务 日本語タスク 한국어 작업 🎉",
                    "status": "pending",
                    "priority": "medium",
                }
            ]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert "中文" in item.content

    @pytest.mark.asyncio
    async def test_very_long_content(self):
        """Test todo with very long content"""
        tool = TodoWriteTool()
        long_content = "A" * 10000
        result = await tool.execute(
            todos=[{"id": "1", "content": long_content, "status": "pending", "priority": "medium"}]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert len(item.content) == 10000

    @pytest.mark.asyncio
    async def test_empty_content(self):
        """Test todo with empty content"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[{"id": "1", "content": "", "status": "pending", "priority": "medium"}]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("1")
        assert item is not None
        assert item.content == ""

    @pytest.mark.asyncio
    async def test_duplicate_ids(self):
        """Test handling of duplicate IDs (should update)"""
        tool = TodoWriteTool()

        # First write
        await tool.execute(
            todos=[{"id": "same-id", "content": "First", "status": "pending", "priority": "low"}]
        )

        # Second write with same ID
        result = await tool.execute(
            todos=[
                {"id": "same-id", "content": "Second", "status": "completed", "priority": "high"}
            ]
        )

        assert result.success

        todo_list = get_todo_list()
        items = todo_list.list_all()
        assert len(items) == 1
        assert items[0].content == "Second"
        assert items[0].status == TodoStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_nonexistent_item(self):
        """Test updating a non-existent item creates it"""
        tool = TodoWriteTool()
        result = await tool.execute(
            todos=[
                {
                    "id": "new-item",
                    "content": "New task",
                    "status": "in_progress",
                    "priority": "high",
                }
            ]
        )

        assert result.success

        todo_list = get_todo_list()
        item = todo_list.get("new-item")
        assert item is not None
        assert item.status == TodoStatus.IN_PROGRESS


# ========== Schema Tests ==========


class TestToolSchemas:
    """Test tool schema generation"""

    def test_todowrite_schema_has_items(self):
        """Test that TodoWriteTool schema includes items definition for array"""
        tool = TodoWriteTool()
        schema = tool.to_openai_schema()

        params = schema["function"]["parameters"]
        todos_param = params["properties"]["todos"]

        assert todos_param["type"] == "array"
        assert "items" in todos_param

        items = todos_param["items"]
        assert items["type"] == "object"
        assert "properties" in items
        assert "id" in items["properties"]
        assert "content" in items["properties"]
        assert "status" in items["properties"]
        assert "priority" in items["properties"]

        # Check status enum
        status_prop = items["properties"]["status"]
        assert "enum" in status_prop
        assert "pending" in status_prop["enum"]
        assert "in_progress" in status_prop["enum"]
        assert "completed" in status_prop["enum"]

    def test_todoread_schema(self):
        """Test TodoReadTool schema"""
        tool = TodoReadTool()
        schema = tool.to_openai_schema()

        assert schema["function"]["name"] == "todoread"
        params = schema["function"]["parameters"]

        # status should have enum
        if "status" in params["properties"]:
            status_prop = params["properties"]["status"]
            assert "enum" in status_prop

    def test_todoclear_schema(self):
        """Test TodoClearTool schema"""
        tool = TodoClearTool()
        schema = tool.to_openai_schema()

        assert schema["function"]["name"] == "todoclear"
        params = schema["function"]["parameters"]

        # mode should have enum
        if "mode" in params["properties"]:
            mode_prop = params["properties"]["mode"]
            assert "enum" in mode_prop
