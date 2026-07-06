# Writing a small interpreter / expression evaluator

For "make a calculator language", "eval math with variables", or a tiny scripting language.
The standard pipeline: tokenize → parse (recursive descent) → evaluate. Do NOT use `eval()`
(unsafe) and don't try to parse with regex alone.

## 1. Tokenize
```python
import re
def tokenize(s):
    return re.findall(r"\d+\.?\d*|[A-Za-z_]\w*|[-+*/()=]", s)
```

## 2. Recursive-descent parser (grammar drives the functions)
Grammar (precedence low→high): `expr = term (('+'|'-') term)*`,
`term = factor (('*'|'/') factor)*`, `factor = NUMBER | NAME | '(' expr ')'`.
```python
class Parser:
    def __init__(self, toks): self.toks, self.i = toks, 0
    def peek(self): return self.toks[self.i] if self.i < len(self.toks) else None
    def eat(self): t = self.peek(); self.i += 1; return t
    def expr(self):
        v = self.term()
        while self.peek() in ("+", "-"):
            op = self.eat(); v = v + self.term() if op == "+" else v - self.term()
        return v
    def term(self):
        v = self.factor()
        while self.peek() in ("*", "/"):
            op = self.eat(); v = v * self.factor() if op == "*" else v / self.factor()
        return v
    def factor(self, env=None):
        t = self.eat()
        if t == "(":
            v = self.expr(); self.eat()  # consume ')'
            return v
        if re.match(r"\d", t): return float(t)
        return VARS.get(t, 0.0)          # variable lookup

VARS = {}
def evaluate(s): return Parser(tokenize(s)).expr()
```
(For variables/assignment `x = 3`, check for a `NAME '='` at the start and store into `VARS`.)

## Why this shape
- One function per grammar rule = clean, correct precedence and parentheses.
- Extend by adding rules (functions, comparisons, `if`). For a full language, build an AST
  (nodes) in the parser and walk it in a separate evaluator.

## Test
Assert `evaluate("2 + 3 * 4") == 14`, `evaluate("(2 + 3) * 4") == 20`, and variable cases.
