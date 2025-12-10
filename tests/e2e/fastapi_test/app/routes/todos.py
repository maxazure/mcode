"""Todo CRUD endpoints"""
from fastapi import APIRouter, HTTPException, status
from app.models import Todo, TodoCreate, TodoUpdate
from app.database import db

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("", response_model=list[Todo])
def list_todos():
    """Get all todos"""
    return db.get_all()


@router.post("", response_model=Todo, status_code=status.HTTP_201_CREATED)
def create_todo(todo: TodoCreate):
    """Create a new todo"""
    return db.create(todo)


@router.get("/{todo_id}", response_model=Todo)
def get_todo(todo_id: int):
    """Get a todo by ID"""
    todo = db.get_by_id(todo_id)
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo with id {todo_id} not found"
        )
    return todo


@router.put("/{todo_id}", response_model=Todo)
def update_todo(todo_id: int, todo_update: TodoUpdate):
    """Update a todo"""
    todo = db.update(todo_id, todo_update)
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo with id {todo_id} not found"
        )
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int):
    """Delete a todo"""
    if not db.delete(todo_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Todo with id {todo_id} not found"
        )
