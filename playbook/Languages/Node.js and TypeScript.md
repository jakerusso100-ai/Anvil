# Node.js and TypeScript

Building a Node/JS/TS CLI, script, or app. Node + npm are the toolchain (`node --version`,
`npm --version`). Give it a `package.json` with a `test` script so Anvil's gate sees the test.

## package.json — always include a `test` script
```json
{
  "name": "mytool",
  "version": "1.0.0",
  "type": "module",
  "bin": { "mytool": "./index.js" },
  "scripts": { "start": "node index.js", "test": "node --test" }
}
```
- `"type": "module"` = use `import`/`export` (ESM). Omit it for CommonJS (`require`).
- `npm test` is the verification command Anvil looks for — make it run your tests.

## Tests with the built-in runner (no deps — Node 18+)
```js
// test/tool.test.js
import { test } from "node:test";
import assert from "node:assert";
import { wordCount } from "../index.js";

test("counts words", () => {
  assert.deepStrictEqual(wordCount("a b a"), { a: 2, b: 1 });
});
```
Run with `node --test` (or `npm test`). Exit 0 = pass. No jest/mocha install needed.

## Skeleton (a CLI that's importable + runnable)
```js
// index.js
export function wordCount(text) {
  const counts = {};
  for (const w of text.split(/\s+/).filter(Boolean)) counts[w] = (counts[w] || 0) + 1;
  return counts;
}
// run as a CLI only when executed directly (so tests can import without side effects)
if (import.meta.url === `file://${process.argv[1]}`) {
  console.log(wordCount(process.argv.slice(2).join(" ")));
}
```

## Gotchas
- Deps: `npm install <pkg>` writes to package.json + node_modules. Commit package.json.
- ESM vs CommonJS: don't mix `import` and `require` in one file; pick via `"type"`.
- TypeScript: `npm install -D typescript`, add `tsconfig.json`, build with `npx tsc`, test the
  compiled JS or use `tsx`/`ts-node`. Keep a `test` script that actually runs.
- Async: use `async/await`; a test that awaits must be `async`.
- Verify by running `npm test` and seeing it exit 0 (see [[Writing a build that passes review]]).
