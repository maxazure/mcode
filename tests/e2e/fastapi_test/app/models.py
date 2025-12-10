"""Pydantic models for Todo items"""
from typing import Optional
from pydantic import BaseModel


class TodoBase(BaseModel):
    """Base Todo model"""

    title: str
    description: Optional[str] = None
    completed: bool = False


class TodoCreate(TodoBase):
    """Model for creating a Todo"""

    pass


class TodoUpdate(BaseModel):
    """Model for updating a Todo"""

    title: Optional[str] = None
    description: Optional[str] = None
    completed: Optional[bool] = None


class Todo(TodoBase):
    """Full Todo model with ID"""

    id: int

    class Config:
        from_attributes = True
