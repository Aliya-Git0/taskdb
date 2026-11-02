"""
Task Manager API: FastAPI + PostgreSQL (psycopg2) + Pydantic

Run:  uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import os
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

# --------------------------------------------------------------- database ---
DB_PARAMS = {
    "dbname": os.getenv("PGDATABASE", "taskdb"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "your_password"),
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5433"),
}


def get_connection():
    return psycopg2.connect(**DB_PARAMS, cursor_factory=RealDictCursor)


def run_query(query, params=(), fetch="none"):
    """Run one query in its own transaction. fetch: 'one' | 'all' | 'none'.
    Returns rows (dict / list of dicts) or the number of affected rows."""
    try:
        with get_connection() as conn:          # commit on success, rollback on error
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return cur.rowcount
    except psycopg2.Error as error:
        raise HTTPException(status_code=500, detail=f"Database error: {error}")


# ---------------------------------------------------------------- models ----
class TaskCreate(BaseModel):
    """Body for POST: what the client sends to create a task."""
    title: str = Field(min_length=1, max_length=200)
    is_completed: bool = False


class TaskUpdate(BaseModel):
    """Body for PUT: every field optional, only sent fields are changed."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    is_completed: Optional[bool] = None


class Task(BaseModel):
    """What the API returns."""
    id: int
    title: str
    is_completed: bool


# ------------------------------------------------------------------- app ----
app = FastAPI(title="Task Manager API")


@app.get("/")
def read_root():
    return {"message": "Task Manager API is running"}


# READ -----------------------------------------------------------------------
@app.get("/api/tasks", response_model=list[Task])
def get_tasks():
    return run_query("SELECT * FROM tasks ORDER BY id;", fetch="all")


@app.get("/api/tasks/{task_id}", response_model=Task)
def get_task_by_id(task_id: int):
    task = run_query("SELECT * FROM tasks WHERE id = %s;", (task_id,), fetch="one")
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# CREATE ---------------------------------------------------------------------
@app.post("/api/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate):
    return run_query(
        "INSERT INTO tasks (title, is_completed) VALUES (%s, %s) RETURNING *;",
        (task.title, task.is_completed),
        fetch="one",
    )


# UPDATE ---------------------------------------------------------------------
@app.put("/api/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, task: TaskUpdate):
    if task.title is None and task.is_completed is None:
        raise HTTPException(status_code=400, detail="Provide title and/or is_completed")

    # COALESCE keeps the old value for any field that was not sent (NULL)
    updated = run_query(
        """
        UPDATE tasks
        SET title        = COALESCE(%s, title),
            is_completed = COALESCE(%s, is_completed)
        WHERE id = %s
        RETURNING *;
        """,
        (task.title, task.is_completed, task_id),
        fetch="one",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


# DELETE ---------------------------------------------------------------------
@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    deleted = run_query("DELETE FROM tasks WHERE id = %s;", (task_id,))
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
