# Flask web app with SQLite

A complete, runnable web app pattern: routes, HTML templates, and a SQLite database that
persists between runs. Needs `python -m pip install flask`. SQLite is in the stdlib.

```python
import sqlite3
from flask import Flask, request, redirect, render_template_string
app = Flask(__name__)
DB = "app.db"

def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, text TEXT, done INT DEFAULT 0)")

PAGE = """<!doctype html><title>Items</title>
<h1>Items</h1>
<form method=post action=/add><input name=text><button>Add</button></form>
<ul>{% for it in items %}
  <li>{{it['text']}} <a href="/del/{{it['id']}}">x</a></li>
{% endfor %}</ul>"""

@app.route("/")
def index():
    with db() as con:
        items = con.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    return render_template_string(PAGE, items=items)

@app.route("/add", methods=["POST"])
def add():
    with db() as con:
        con.execute("INSERT INTO items (text) VALUES (?)", (request.form["text"],))
    return redirect("/")

@app.route("/del/<int:i>")
def delete(i):
    with db() as con:
        con.execute("DELETE FROM items WHERE id=?", (i,))
    return redirect("/")

if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=True)
```

## Rules that avoid bugs
- ALWAYS use parameterized queries (`?` placeholders) — never f-string SQL (injection).
- Call `init_db()` at startup so a fresh clone works with no DB file.
- `sqlite3.Row` lets you access columns by name (`row["text"]`).
- For real templates, put HTML in `templates/` and use `render_template("x.html")`.

## Self-test (headless — no server needed)
Use Flask's test client: `client = app.test_client(); r = client.get("/"); assert r.status_code == 200`.
POST to `/add`, then GET `/` and assert the new item text is in `r.data`. Exits without
binding a port. See [[Writing a build that passes review]].
