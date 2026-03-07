# Veritas (v1.2.0)

> *A programming language designed to resemble clear, structured human English while remaining deterministic and easy to parse.*

Veritas compiles `.ver` source files to C via a Python transpiler (`vcparser.py`). Programs read like well-structured English instructions — every statement follows strict grammatical rules that map unambiguously to C output.

Version 1.2.0 introduces first-class managed strings, an intelligent prelude system, and built-in support for industry-standard scientific libraries.

---

## Development Disclaimer

**Veritas** is the creation of a single designer who is an Electrical and Mechanical Engineer (EE/ME) by trade, rather than a computer scientist. While the language's core philosophy, syntax rules, and architectural structure were designed solely by the creator, an **AI agentic workflow** was utilized extensively to implement the Python-based parser and transpiler logic. This collaboration allowed for the rapid realization of a domain-specific language tailored for researchers and engineers.

---

## Key Features

- **Natural Syntax**: Statements like `Create 'x' as an integer with value 10.`
- **Managed Strings**: First-class `string` type. No more manual `char*` buffers. Concatenate with `Call 'join'` and compare with `is equal to`.
- **Intelligent Prelude**: Common C headers (`stdio.h`, `math.h`, etc.) are included automatically. Scientific headers like `complex.h`, `fftw3.h`, and `gsl_statistics.h` are injected when needed.
- **Blessed Libraries**: Call high-performance functions like `mean`, `standard_deviation`, and `fft_forward` directly.
- **Strict Grammar**: Deterministic list formatting ensures clarity:
    - 1 item: `X`
    - 2 items: `X and Y`
    - 3+ items: `X, Y, and Z` (Oxford comma required).
- **Direct C Interop**: Use any C type directly (e.g., `uint32_t`).
- **Complex Arithmetic**: Native support for imaginary literals like `1j` and `4.2j`.

---

## Documentation

The full language specification is in [`REGULA.html`](./REGULA.html) — the *Regula Veritatis*, the Rule of Truth.

To read it locally, open the file in any browser:

```bash
open REGULA.html        # macOS
xdg-open REGULA.html    # Linux
start REGULA.html       # Windows
```

Or view it at GitHub Pages:

[https://jreyes913.github.io/veritas/REGULA.html](https://jreyes913.github.io/veritas/REGULA.html)

---


## Arena Allocator & String Runtime

Generated C programs use a 16MB arena allocator. Strings created via `Call 'join'` or `string` declarations are automatically managed within the arena.

```c
/* Generated C Example */
Arena arena = arena_create(16 * 1024 * 1024);
global_arena = &arena;

char* *name = arena_alloc(&arena, sizeof(char*));
*name = join("Jose", "Reyes");

if (strcmp(*name, "JoseReyes") == 0) {
    printf("Managed strings work!\n");
}

arena_destroy(&arena);
```

---

## Installation

**Requirements**
- Python 3.10+
- GCC

**Clone the repo**

```bash
git clone https://github.com/jreyes913/veritas.git
cd veritas
```

**Compile a `.ver` file**

```bash
bash veritasc.sh example.ver
./example
```

`veritasc.sh` handles transpilation, linking with the `runtime.c` support file, and library detection in one step.

---

## Syntax Highlighting & File Icon

The `veritas-language/` folder contains a VS Code extension that provides:

- Syntax highlighting for `.ver` files (including support for `j` literals)
- A file icon in the Explorer sidebar

### Installation

```bash
cp -r veritas-language ~/.vscode/extensions/
```

or

```bash
cd veritas-language
vsce package
```

Then install VSIX package in VS Code.

Restart VS Code to activate.

---

## Repository Structure

```
.
├── REGULA.html              # Full language specification (styled)
├── vcparser.py              # Veritas → C transpiler compatibility entrypoint
├── compiler/
│   ├── main.py              # Main compiler entrypoint
│   ├── legacy.py            # Core parser and code generator
│   ├── runtime.c            # C runtime for strings and scientific helpers
│   ├── frontend/            # Lexer and Parser
│   ├── semantic/            # Semantic Analyzer and Symbol Table
│   └── ir/                  # Intermediate Representation and Lowering
├── veritasc.sh              # Build script (transpile + compile + link)
├── tests/                   # Test suite (finance, physics, math, statistics)
├── .gitignore               # .gitignore (excludes binaries and .c files)
├── veritas-language/        # VS Code extension
└── README.md
```

---

## Contact

**Jose Reyes**  
Email: [jstunner55@gmail.com](mailto:jstunner55@gmail.com)  
LinkedIn: [jose-reyes-634768264](https://www.linkedin.com/in/jose-reyes-634768264/)

---

## License

MIT
