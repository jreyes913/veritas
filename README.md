# Veritas (v1.4.0)

> *A programming language designed to resemble clear, structured human English while remaining deterministic and easy to parse.*

Veritas compiles `.ver` source files to C via a Python transpiler (`vcparser.py`). Programs read like well-structured English instructions — every statement follows strict grammatical rules that map unambiguously to C output.

Version 1.4.0 introduces first-class **Data Persistence** with `Load` and `Save` statements, enabling CSV and binary matrix I/O.

---

## Development Disclaimer

**Veritas** is the creation of a single designer who is an Electrical and Mechanical Engineer (EE/ME) by trade, rather than a computer scientist. While the language's core philosophy, syntax rules, and architectural structure were designed solely by the creator, an **AI agentic workflow** was utilized extensively to implement the Python-based parser and transpiler logic. This collaboration allowed for the rapid realization of a domain-specific language tailored for researchers and engineers.

---

## Key Features

- **Natural Syntax**: Statements like `Create 'x' as an integer with value 10.`
- **Managed Data Structures**:
    - **Vectors**: Numeric-only sequences with math support (`plus`, `minus`, `multiplied by`).
    - **Arrays**: Non-numeric sequences for strings or other types.
    - **Matrices**: Multi-dimensional structures for math or mixed data.
- **Data I/O**: Load and Save matrices from CSV or Binary files (`Load 'data' from "input.csv" as matrix`).
- **Managed Strings**: First-class `string` type. Concatenate with `Call 'join'` and compare with `is equal to`.
- **Advanced Math**: Native support for **Exponents** (`raised to the`) and **Complex Arithmetic** (`1j`, `4.2j`).
- **Indexed Access**: Create variables from elements (`Create 'x' as an element of 'arr' at index 0`) or update them directly (`Replace 'arr' at index 0 with 5`).
- **Intelligent Prelude**: Common C headers (`stdio.h`, `math.h`, etc.) are included automatically. Scientific headers like `complex.h`, `fftw3.h`, and `gsl_statistics.h` are injected when needed.
- **Strict Grammar**: Deterministic list formatting ensures clarity:
    - 1 item: `X`
    - 2 items: `X and Y` (No commas).
    - 3+ items: `X, Y, and Z` (Oxford comma required).
- **Direct C Interop**: Use any C type directly (e.g., `uint32_t`).

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
# Locally
./veritas example.ver

# Or after installing globally (see below)
veritas example.ver
```

### Global Installation

To run `veritas` from anywhere:

```bash
sudo ln -s "$(pwd)/veritas" /usr/local/bin/veritas
```

Then you can simply run:
```bash
veritas example.ver
```

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
├── veritas                  # Build script (transpile + compile + link)
├── examples/                # Example programs (finance, physics, math, statistics)
├── tests/                   # Compiler unit tests and error handling cases
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
