# Veritas (v1.1.0)

> *A programming language designed to resemble clear, structured human English while remaining deterministic and easy to parse.*

Veritas compiles `.ver` source files to C via a Python transpiler (`vcparser.py`). Programs read like well-structured English instructions — every statement follows strict grammatical rules that map unambiguously to C output.

Version 1.1.0 introduces significant improvements to the type system and expression parsing, including multi-word C types, pointer syntax, and complex arithmetic through quantity grouping.

---

## Key Features

- **Natural Syntax**: Statements like `Create 'x' as an integer with value 10.`
- **Direct C Interop**: Use any C type directly (e.g., `double complex`, `uint32_t`).
- **Pointer Support**: First-class support for addresses and pointer dereferencing.
- **Quantity Expressions**: Nested grouping with `the quantity` allows for complex mathematical formulas.
- **English Articles**: Use `a` or `an` naturally; the compiler handles the stripping.

---

## Documentation

The full language specification is in [`REGULA.html`](./REGULA.html) — the *Regula Veritatis*, the Rule of Truth.

To read it locally, open the file in any browser:

```bash
open REGULA.html        # macOS
xdg-open REGULA.html    # Linux
start REGULA.html       # Windows
```

Or view it at Github Pages:

```
https://jreyes913.github.io/veritas/REGULA.html
```

---


## Arena Allocator Runtime Example

Generated C programs now use a 16MB arena allocator and allocate variables from the arena.

```c
Arena arena = arena_create(16 * 1024 * 1024);

int *x = arena_alloc(&arena, sizeof(int));
double *t = arena_alloc(&arena, 100 * sizeof(double));

*x = 5;
for (int i = 0; i < 100; i++) {
    t[i] = (double)i * 0.5;
}

printf("x = %d\n", *x);
for (int i = 0; i < 5; i++) {
    printf("t[%d] = %.2f\n", i, t[i]);
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
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

**Compile a `.ver` file**

```bash
bash veritasc.sh example.ver
./example
```

`veritasc.sh` handles transpilation and compilation in one step. It automatically detects which libraries are included in your `.ver` source and passes the correct linker flags to GCC.

---

## Syntax Highlighting & File Icon

The `veritas-language/` folder contains a VS Code extension that provides:

- Syntax highlighting for `.ver` files
- A file icon in the Explorer sidebar

### Option A — Local installation (VS Code on your machine)

```bash
cp -r veritas-language ~/.vscode/extensions/
```

Restart VS Code. The extension loads automatically.

### Option B — Remote server via VS Code Remote-SSH

If you edit files on a remote server using the Remote-SSH extension, install it on the **server**, not your local machine:

```bash
# On the remote server
mkdir -p ~/.vscode-server/extensions/
cp -r veritas-language ~/.vscode-server/extensions/
```

Then in VS Code: `Ctrl+Shift+P` → **Developer: Reload Window**.

If the extension does not appear in **Show Running Extensions** after reloading, clear the extension cache and reconnect:

```bash
# On the remote server
rm -rf ~/.vscode-server/data/CachedExtensions/
```

Then close the Remote-SSH connection from your laptop (`Ctrl+Shift+P` → **Remote: Close Remote Connection**) and reconnect.

### Verifying the extension is active

`Ctrl+Shift+P` → **Developer: Show Running Extensions** — `veritas-language` should appear in the list. Open any `.ver` file to confirm syntax highlighting is active.

### Token colors

The extension maps Veritas tokens to VS Code's theme colors by default. For higher contrast, add the following to your VS Code user settings (`Ctrl+Shift+P` → **Preferences: Open User Settings (JSON)**):

```json
"editor.tokenColorCustomizations": {
    "textMateRules": [
        { "scope": "keyword.control.program.start.veritas", "settings": { "foreground": "#FF4D6D", "fontStyle": "bold" } },
        { "scope": "keyword.control.program.end.veritas", "settings": { "foreground": "#FF758F", "fontStyle": "bold" } },
        { "scope": "keyword.control.include.veritas", "settings": { "foreground": "#FFB703", "fontStyle": "bold" } },
        { "scope": "keyword.control.function.start.veritas", "settings": { "foreground": "#3A86FF", "fontStyle": "bold" } },
        { "scope": "keyword.control.function.end.veritas", "settings": { "foreground": "#4CC9F0", "fontStyle": "bold" } },
        { "scope": "keyword.control.declaration.veritas", "settings": { "foreground": "#80ED99", "fontStyle": "bold" } },
        { "scope": "keyword.control.assignment.veritas", "settings": { "foreground": "#2EC4B6", "fontStyle": "bold" } },
        { "scope": "keyword.control.call.veritas", "settings": { "foreground": "#06D6A0", "fontStyle": "bold" } },
        { "scope": "keyword.control.loop.start.veritas", "settings": { "foreground": "#8338EC", "fontStyle": "bold" } },
        { "scope": "keyword.control.loop.end.veritas", "settings": { "foreground": "#B5179E", "fontStyle": "bold" } },
        { "scope": "keyword.control.conditional.if.veritas", "settings": { "foreground": "#FB5607", "fontStyle": "bold" } },
        { "scope": "keyword.control.conditional.else.veritas", "settings": { "foreground": "#FF006E", "fontStyle": "bold" } },
        { "scope": "keyword.control.conditional.end.veritas", "settings": { "foreground": "#E5383B", "fontStyle": "bold" } },
        { "scope": "keyword.other.veritas", "settings": { "foreground": "#FFD166" } },
        { "scope": "storage.type.veritas", "settings": { "foreground": "#00F5D4", "fontStyle": "bold" } },
        { "scope": "keyword.operator.veritas", "settings": { "foreground": "#FF9F1C", "fontStyle": "bold" } },
        { "scope": "variable.other.veritas", "settings": { "foreground": "#90E0EF" } },
        { "scope": "string.quoted.double.veritas", "settings": { "foreground": "#C1FBA4" } },
        { "scope": "constant.numeric.veritas", "settings": { "foreground": "#C77DFF", "fontStyle": "bold" } },
        { "scope": "comment.block.veritas", "settings": { "foreground": "#5C677D", "fontStyle": "italic" } },
        { "scope": "punctuation.terminator.veritas", "settings": { "foreground": "#F94144", "fontStyle": "bold" } }
    ]
}
```

---

## Repository Structure

```
.
├── REGULA.html              # Full language specification (styled)
├── vcparser.py              # Veritas → C transpiler
├── veritasc.sh              # Build script (transpile + compile)
├── example.ver              # Example Veritas program
├── .gitignore               # .gitignore
├── veritas-language/        # VS Code extension
│   ├── package.json
│   ├── language-configuration.json
│   ├── icons/
│   │   └── veritas.svg
│   └── syntaxes/
│       └── veritas.tmLanguage.json
└── README.md
```

---

## License

MIT
