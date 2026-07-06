# Tkinter desktop app with persistence

Tkinter is in the stdlib (no install) — good for simple desktop GUIs: to-do lists,
note apps, calculators, forms. Persist state to a JSON file so it survives restarts.

```python
import json, tkinter as tk
from pathlib import Path
STORE = Path("tasks.json")

class App:
    def __init__(self, root):
        self.tasks = json.loads(STORE.read_text()) if STORE.exists() else []
        self.entry = tk.Entry(root, width=30); self.entry.pack(pady=4)
        tk.Button(root, text="Add", command=self.add).pack()
        self.box = tk.Listbox(root, width=40); self.box.pack(pady=4)
        self.box.bind("<Double-Button-1>", self.remove)
        self.refresh()

    def add(self):
        t = self.entry.get().strip()
        if t:
            self.tasks.append(t); self.entry.delete(0, tk.END); self.save(); self.refresh()

    def remove(self, _):
        sel = self.box.curselection()
        if sel:
            del self.tasks[sel[0]]; self.save(); self.refresh()

    def save(self):    STORE.write_text(json.dumps(self.tasks))
    def refresh(self):
        self.box.delete(0, tk.END)
        for t in self.tasks: self.box.insert(tk.END, t)

if __name__ == "__main__":
    root = tk.Tk(); root.title("Tasks"); App(root); root.mainloop()
```

## Gotchas
- `mainloop()` blocks (opens a window) — do NOT call it in a self-test. Test the logic
  instead: construct with a `tk.Tk()` you `.withdraw()`, call `add()`/`remove()`, and assert
  `self.tasks` + that the JSON file was written. On a headless box tkinter may need a
  display; wrap the window creation in try/except and test the pure data methods.
- Keep data logic (add/remove/save/load) separate from widgets so it's unit-testable.
- For a richer native GUI, Anvil itself uses PySide6/Qt — heavier but far more capable.
