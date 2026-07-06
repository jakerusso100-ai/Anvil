# Python on Windows - use python, not python3

On Windows, `python3` is very often the **Microsoft Store stub** — a fake `python3.exe`
in `...\WindowsApps\` that either opens the Store or runs a *different* interpreter than
the one your packages are installed in. This silently breaks builds: you `pip install X`,
then `python3 yourfile.py` can't import X.

## Do this
- Run scripts with **`python`** (not `python3`): `python game.py --selftest`
- Install deps with **`python -m pip install X`** — the `-m` guarantees the package lands
  in the SAME interpreter you run, avoiding the pip/python mismatch.
- Check what you're on: `python --version` and `python -c "import sys; print(sys.executable)"`

## Symptoms of the stub / mismatch (and the fix)
- `ModuleNotFoundError` for a package you just installed → you installed to a different
  interpreter. Reinstall with `python -m pip install X` and run with `python`.
- `python3` prints nothing / opens the Store / "was not found" → use `python`.

## Verifying a dependency is importable before you rely on it
```bash
python -c "import chess; print('chess', chess.__version__)"
python -c "import panda3d; print('panda3d ok')"
```
If that prints cleanly, the library is usable from `python`. Build against that.
