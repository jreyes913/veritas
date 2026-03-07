# Veritas (v1.5.0)

> *A programming language designed to resemble clear, structured human English while remaining deterministic and easy to parse.*

Veritas compiles `.ver` source files to C via a Python transpiler. Programs read like well-structured English instructions — every statement follows strict grammatical rules that map unambiguously to C output.

Version 1.5.0 introduces a first-class **Units & Dimensional Analysis** system and automated **LaTeX Report Generation**.

---

## Development Disclaimer

**Veritas** is the creation of a single designer who is an Electrical and Mechanical Engineer (EE/ME) by trade, rather than a computer scientist. While the language's core philosophy, syntax rules, and architectural structure were designed solely by the creator, an **AI agentic workflow** was utilized extensively to implement the Python-based parser and transpiler logic. This collaboration allowed for the rapid realization of a domain-specific language tailored for researchers and engineers.

---

## Key Features

- **Natural Syntax**: Statements like `Create 'x' as an integer with value 10.`
- **Units & Dimensional Analysis**: Define dimensions and units (SI/Imperial). The compiler verifies dimensional consistency at compile-time (e.g., catching `kg + m` errors).
- **Automated Reporting**: Export variables directly to LaTeX reports using the `Export` statement and `veritas report`.
- **Managed Data Structures**:
    - **Vectors**: Numeric-only sequences with math support (`plus`, `minus`, `multiplied by`).
    - **Arrays**: Non-numeric sequences for strings or other types.
    - **Matrices**: Multi-dimensional structures for math or mixed data.
- **Data I/O**: Load and Save matrices from CSV or Binary files (`Load 'data' from "input.csv" as matrix`).
- **Managed Strings**: First-class `string` type. Concatenate with `Call 'join'` and compare with `is equal to`.
- **Advanced Math**: Native support for **Exponents** (`raised to the`) and **Complex Arithmetic** (`1j`, `4.2j`).
- **Strict Grammar**: Deterministic list formatting ensures clarity (Oxford comma required for 3+ items).

---

## Documentation

The full language specification is in [`REGULA.html`](./REGULA.html) — the *Regula Veritatis*, the Rule of Truth.

To read it locally, open the file in any browser:

```bash
xdg-open REGULA.html    # Linux
open REGULA.html        # macOS
start REGULA.html       # Windows
```

Or view it at GitHub Pages:
[https://jreyes913.github.io/veritas/REGULA.html](https://jreyes913.github.io/veritas/REGULA.html)

---

## Installation

**Requirements**
- Python 3.10+
- GCC
- (Optional) PDFLaTeX for report compilation

**Setup**

```bash
git clone https://github.com/jreyes913/veritas.git
cd veritas
# Install globally
sudo ln -s "$(pwd)/compiler/main.py" /usr/local/bin/veritas
```

---

## CLI Usage

Veritas now features a unified CLI for the entire development lifecycle:

```bash
veritas new my_project      # Create a new project structure
cd my_project
veritas build               # Compile src/main.ver to binary
veritas run                 # Build and execute the program
veritas test                # Run unit and integration tests
veritas report              # Generate LaTeX/PDF report from exports
```

---

## Units System Example

```veritas
Include 'units.ver'.

Create 'mass' as a double<kilogram> with value 5.0.
Create 'accel' as a double<acceleration> with value 9.8.

/* The compiler verifies that Newton = kg * m/s^2 */
Create 'force' as a double<Newton> with value 'mass' multiplied by 'accel'.

Export 'force' as 'Total Force' for report.
```

---

## Repository Structure

```
.
├── REGULA.html              # Full language specification (styled)
├── compiler/
│   ├── cli.py               # Unified CLI implementation
│   ├── config.py            # Project configuration (veritas.toml)
│   ├── legacy.py            # Core parser and code generator
│   ├── semantic/            # Semantic & Dimensional Analysis
│   └── std/                 # Standard Library (units.ver)
├── examples/                # Example programs
├── tests/                   # Compiler tests
└── veritas-language/        # VS Code extension
```

---

## License

MIT
