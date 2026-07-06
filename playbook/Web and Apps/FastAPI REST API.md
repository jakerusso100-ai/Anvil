# FastAPI REST API with SQLite

A typed JSON REST API. Needs `python -m pip install fastapi uvicorn`. FastAPI gives you
validation (via Pydantic), auto docs at `/docs`, and a test client for headless self-tests.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3

app = FastAPI()
DB = "api.db"
def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; return con
with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY, title TEXT, done INT DEFAULT 0)")

class Todo(BaseModel):
    title: str
    done: bool = False

@app.get("/todos")
def list_todos():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM todos")]

@app.post("/todos")
def add_todo(t: Todo):
    with db() as c:
        cur = c.execute("INSERT INTO todos (title, done) VALUES (?,?)", (t.title, int(t.done)))
        return {"id": cur.lastrowid, **t.dict()}

@app.delete("/todos/{tid}")
def del_todo(tid: int):
    with db() as c:
        if not c.execute("SELECT 1 FROM todos WHERE id=?", (tid,)).fetchone():
            raise HTTPException(404, "not found")
        c.execute("DELETE FROM todos WHERE id=?", (tid,))
    return {"deleted": tid}

# run: uvicorn main:app --reload    (module:app)
```

## Self-test (headless, no server)
```python
from fastapi.testclient import TestClient
def run_selftest():
    c = TestClient(app)
    r = c.post("/todos", json={"title": "buy milk"}); assert r.status_code == 200
    tid = r.json()["id"]
    assert any(t["title"] == "buy milk" for t in c.get("/todos").json())
    assert c.delete(f"/todos/{tid}").status_code == 200
    print("[selftest] API OK")
```
`TestClient` exercises every route in-process, no port binding — perfect for the self-test gate.
