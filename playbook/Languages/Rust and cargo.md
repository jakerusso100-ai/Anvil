# Rust and cargo

Building a Rust CLI/library. Cargo is the toolchain (`cargo --version`, `rustc --version`).
`cargo test` is the verification command — write real `#[test]` functions.

## Project (cargo makes the layout)
`cargo new mytool` creates `Cargo.toml` + `src/main.rs`. `cargo new --lib` for a library.
```
mytool/
  Cargo.toml
  src/main.rs     # or src/lib.rs
```

## Skeleton with inline tests
```rust
// src/main.rs
use std::collections::HashMap;

fn word_count(text: &str) -> HashMap<&str, usize> {
    let mut counts = HashMap::new();
    for w in text.split_whitespace() {
        *counts.entry(w).or_insert(0) += 1;
    }
    counts
}

fn main() {
    let text = std::env::args().skip(1).collect::<Vec<_>>().join(" ");
    println!("{:?}", word_count(&text));
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn counts_words() {
        let c = word_count("a b a");
        assert_eq!(c.get("a"), Some(&2));
        assert_eq!(c.get("b"), Some(&1));
    }
}
```
Verify: `cargo test` (exit 0 = pass). `cargo run -- some text` to run. `cargo build` to compile.

## Error handling — the Rust way
- Return `Result<T, E>`; propagate with `?`. `main` can be `fn main() -> Result<(), Box<dyn std::error::Error>>`.
- Handle `Option` with `match`, `if let Some(x)`, `.unwrap_or(default)` — avoid bare `.unwrap()` in real code (it panics).
- No nulls; no exceptions. The compiler forces you to handle both variants.

## Gotchas (the borrow checker)
- Ownership: a value has one owner; borrow with `&` (shared) or `&mut` (exclusive, one at a time).
- Lifetimes: returning a reference tied to an input needs a lifetime (`fn f<'a>(x: &'a str) -> &'a str`).
- `String` (owned) vs `&str` (borrowed) — take `&str` as function args.
- Add deps with `cargo add <crate>` (writes Cargo.toml). Compile errors are precise — read them.
See [[Writing a build that passes review]].
