"""FastAPI Todo Application"""
from fastapi import FastAPI
from app.routes.todos import router as todos_router

app = FastAPI(
    title="Todo API",
    description="A simple Todo list API",
    version="1.0.0",
)

# Include routers
app.include_router(todos_router)


@app.get("/")
def root():
    """Root endpoint"""
    return {"message": "Welcome to Todo API", "docs": "/docs"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
