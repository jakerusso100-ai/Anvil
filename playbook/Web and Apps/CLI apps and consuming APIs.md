# CLI apps (argparse) and consuming web APIs

## Command-line apps with argparse (stdlib)
```python
import argparse
def main(argv=None):
    p = argparse.ArgumentParser(description="What this tool does")
    p.add_argument("input", help="file to process")
    p.add_argument("-n", "--count", type=int, default=1, help="how many times")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--selftest", action="store_true", help="run a headless check and exit")
    args = p.parse_args(argv)
    if args.selftest:
        assert do_work("demo", 2) is not None
        print("[selftest] OK"); return 0
    print(do_work(args.input, args.count))
    return 0

def do_work(inp, count): return inp * count

if __name__ == "__main__":
    raise SystemExit(main())
```
- `main(argv=None)` + `parse_args(argv)` makes it testable: call `main(["file", "-n", "3"])`.
- Return an int exit code; `raise SystemExit(main())` propagates it.
- Add `--selftest` so the build's self-test gate can verify it (see [[Writing a build that passes review]]).

## Consuming web APIs with requests
```python
import requests
r = requests.get("https://api.example.com/data", params={"q": "term"}, timeout=10)
r.raise_for_status()          # turn 4xx/5xx into an exception
data = r.json()
```
- ALWAYS pass `timeout=` — a hung request otherwise blocks forever.
- `raise_for_status()` so failures are loud, not silent.
- Wrap network calls in try/except `requests.RequestException` and degrade gracefully.
- Respect rate limits; cache responses when polling. For POST, use `json=payload`.
