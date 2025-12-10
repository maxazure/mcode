"""In-memory database simulation"""
from typing import Optional
from app.models import Todo, TodoCreate, TodoUpdate


class TodoDatabase:
    """Simple in-memory todo database"""

    def __init__(self):
        self._todos: dict[int, Todo] = {}
        self._counter: int = 0

    def get_all(self) -> list[Todo]:
        """Get all todos"""
        return list(self._todos.values())

    def get_by_id(self, todo_id: int) -> Optional[Todo]:
        """Get a todo by ID"""
        return self._todos.get(todo_id)

    def create(self, todo: TodoCreate) -> Todo:
        """Create a new todo"""
        self._counter += 1
        new_todo = Todo(
            id=self._counter,
            title=todo.title,
            description=todo.description,
            completed=todo.completed,
        )
        self._todos[new_todo.id] = new_todo
        return new_todo

    def update(self, todo_id: int, todo_update: TodoUpdate) -> Optional[Todo]:
        """Update an existing todo"""
        if todo_id not in self._todos:
            return None

        existing = self._todos[todo_id]
        update_data = todo_update.model_dump(exclude_unset=True)

        updated_todo = Todo(
            id=existing.id,
            title=update_data.get("title", existing.title),
            description=update_data.get("description", existing.description),
            completed=update_data.get("completed", existing.completed),
        )
        self._todos[todo_id] = updated_todo
        return updated_todo

    def delete(self, todo_id: int) -> bool:
        """Delete a todo by ID"""
        if todo_id in self._todos:
            del self._todos[todo_id]
            return True
        return False


# Global database instance
db = TodoDatabase()
