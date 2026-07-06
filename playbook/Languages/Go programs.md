# Go programs

Building a Go CLI/service. Go is the toolchain (`go version`). `go test ./...` is the
verification command — write `_test.go` files with `TestXxx` functions.

## Project
`go mod init mytool` creates `go.mod`. Layout:
```
mytool/
  go.mod
  main.go
  wordcount.go
  wordcount_test.go
```

## Skeleton + test
```go
// wordcount.go
package main

import "strings"

func WordCount(text string) map[string]int {
    counts := map[string]int{}
    for _, w := range strings.Fields(text) {
        counts[w]++
    }
    return counts
}
```
```go
// wordcount_test.go
package main

import "testing"

func TestWordCount(t *testing.T) {
    c := WordCount("a b a")
    if c["a"] != 2 || c["b"] != 1 {
        t.Fatalf("got %v", c)
    }
}
```
```go
// main.go
package main

import ("fmt"; "os"; "strings")

func main() {
    fmt.Println(WordCount(strings.Join(os.Args[1:], " ")))
}
```
Verify: `go test ./...` (exit 0 = pass). `go run .` to run. `go build` to compile a binary.

## Idioms & gotchas
- Error handling: functions return `(result, error)`; check `if err != nil { return err }`
  every time. No exceptions.
- Exported names are Capitalized (public); lowercase = package-private.
- `gofmt`/`go fmt` formats code; unused imports/vars are COMPILE ERRORS (remove them).
- Slices/maps are references; `append` may reallocate — reassign: `s = append(s, x)`.
- Add deps: `go get <module>` (updates go.mod/go.sum). Concurrency: goroutines + channels.
See [[Writing a build that passes review]].
