# C# and .NET

Building a C#/.NET console app or library. The `dotnet` CLI is the toolchain
(`dotnet --version`). `dotnet test` is the verification command.

## Projects
```
dotnet new console -o MyTool        # console app -> MyTool/Program.cs + MyTool.csproj
dotnet new xunit   -o MyTool.Tests  # test project (xUnit)
cd MyTool.Tests && dotnet add reference ../MyTool/MyTool.csproj
```
Or keep it simple with one app project and a Main-based self-check.

## Library + app (top-level statements)
```csharp
// MyTool/WordCounter.cs
namespace MyTool;
public static class WordCounter {
    public static Dictionary<string,int> Count(string text) {
        var counts = new Dictionary<string,int>();
        foreach (var w in text.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            counts[w] = counts.GetValueOrDefault(w) + 1;
        return counts;
    }
}
```
```csharp
// MyTool/Program.cs  (top-level statements — no Main boilerplate)
using MyTool;
var text = string.Join(' ', args);
foreach (var (w, n) in WordCounter.Count(text)) Console.WriteLine($"{w}: {n}");
```

## Test (xUnit)
```csharp
// MyTool.Tests/WordCounterTests.cs
using Xunit; using MyTool;
public class WordCounterTests {
    [Fact]
    public void CountsWords() {
        var c = WordCounter.Count("a b a");
        Assert.Equal(2, c["a"]);
        Assert.Equal(1, c["b"]);
    }
}
```
Verify: `dotnet test` (exit 0 = pass). `dotnet run --project MyTool -- some text` to run.
`dotnet build` to compile.

## Gotchas
- Nullable reference types are on by default in new projects — handle `null` or use `?`.
- `csproj` files list deps (`dotnet add package <name>`) and target framework (`net8.0`).
- Namespaces + file-scoped `namespace X;` (semicolon) keep files flat.
- `async Task` methods; `await` async calls; `Main` can be `async Task`.
See [[Writing a build that passes review]].
