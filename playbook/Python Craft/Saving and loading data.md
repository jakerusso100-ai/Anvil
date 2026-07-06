# Saving and loading data (persistence)

"Remember my stuff between runs" = write to disk on change, load on startup. Pick by need.

## JSON — human-readable, for config and simple state
```python
import json
from pathlib import Path
STORE = Path("save.json")

def load():
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}

def save(data):
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
```
- Handles dict/list/str/int/float/bool/None. NOT sets, tuples-as-tuples, dataclasses,
  or datetimes — convert those first (`list(myset)`, `dataclasses.asdict(obj)`, `dt.isoformat()`).
- Always load defensively: if the file is missing or corrupt, fall back to a default.

## SQLite — for queryable/relational data (stdlib, no install)
```python
import sqlite3
con = sqlite3.connect("app.db"); con.row_factory = sqlite3.Row
con.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT)")
con.execute("INSERT INTO notes (body) VALUES (?)", ("hello",))   # parameterized!
con.commit()
rows = con.execute("SELECT * FROM notes").fetchall()
```
Use for many records, search, or relationships. Always parameterize (`?`), never f-string SQL.

## pickle — arbitrary Python objects (only for data YOU created)
```python
import pickle
pickle.dump(obj, open("state.pkl", "wb"))
obj = pickle.load(open("state.pkl", "rb"))
```
NEVER unpickle untrusted data (it can execute code). Prefer JSON for interchange.

## Robust write pattern
Write to a temp file then rename, so a crash mid-write can't corrupt the save:
`tmp = STORE.with_suffix(".tmp"); tmp.write_text(...); tmp.replace(STORE)`.
