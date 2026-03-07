import argparse
import os
import sys
import subprocess
import time
import json
import re
from compiler.legacy import compile_veritas
from compiler.config import load_config

def cmd_new(args):
    name = args.name
    if os.path.exists(name):
        print(f"Error: Directory '{name}' already exists.")
        sys.exit(1)
    
    os.makedirs(name)
    os.makedirs(os.path.join(name, "src"))
    os.makedirs(os.path.join(name, "tests"))
    
    with open(os.path.join(name, "veritas.toml"), "w") as f:
        f.write(f"""[package]
name = "{name}"
version = "0.1.0"
authors = ["Your Name <you@example.com>"]

[dependencies]

[build]
c_compiler = "gcc"
c_flags = ["-O3", "-Wall", "-lm"]
output_dir = "build"
""")

    with open(os.path.join(name, "src", "main.ver"), "w") as f:
        f.write(f"""This is the program '{name}'.

Create 'x' as an int with value 42.
Call 'printf' with "Hello, Veritas!\\n" stored to nothing.
Export 'x' as 'TheAnswer'.

End of the program '{name}'.
""")

    with open(os.path.join(name, "report.vtex"), "w") as f:
        f.write(r"""\documentclass{article}
\begin{document}
\section{Veritas Report}
The answer is \veritas{TheAnswer}.
\end{document}
""")

    print(f"Created new project: {name}")

def cmd_build(args):
    config = load_config()
    if not os.path.exists("src/main.ver"):
        print("Error: src/main.ver not found. Are you in a Veritas project?")
        sys.exit(1)

    print(f"[Veritas] Building {config.name} v{config.version}...")
    start_time = time.time()

    with open("src/main.ver", "r") as f:
        source = f.read()

    # Transpile to C
    try:
        c_code = compile_veritas(source, base_dir=os.path.abspath("src"))
    except Exception as e:
        print(f"Error during transpilation: {e}")
        sys.exit(1)

    # Output C file
    os.makedirs(config.build.output_dir, exist_ok=True)
    c_path = os.path.join(config.build.output_dir, "main.c")
    with open(c_path, "w") as f:
        f.write(c_code)

    # Compile C to binary
    bin_path = os.path.join(config.build.output_dir, config.name)
    cmd = [config.build.c_compiler] + config.build.c_flags + ["-o", bin_path, c_path]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("C Compilation Failed:")
        print(result.stderr)
        sys.exit(1)

    elapsed = time.time() - start_time
    print(f"Success ({elapsed:.2f}s)")

def cmd_run(args):
    cmd_build(args)
    config = load_config()
    bin_path = os.path.join(config.build.output_dir, config.name)
    print(f"[Veritas] Running {config.name}...")
    subprocess.run([bin_path])

def cmd_check(args):
    print("[Veritas] Checking syntax...")
    if not os.path.exists("src/main.ver"):
        print("Error: src/main.ver not found.")
        sys.exit(1)

    with open("src/main.ver", "r") as f:
        source = f.read()
    
    try:
        # Just run pipeline up to C generation (which includes semantic checks)
        compile_veritas(source)
        print("No issues found.")
    except Exception as e:
        print(f"Check Failed: {e}")
        sys.exit(1)

def cmd_report(args):
    # 1. Build and Run to get data
    print("[Veritas] Generating report...")
    cmd_run(args)
    
    # 2. Check for template
    template_path = args.template
    if not os.path.exists(template_path):
        print(f"Error: Template file '{template_path}' not found.")
        sys.exit(1)
        
    # 3. Read data
    data_path = "veritas_exports.json"
    if not os.path.exists(data_path):
        print("Error: No export data found. Did the program run successfully?")
        sys.exit(1)
        
    with open(data_path, "r") as f:
        data = json.load(f)
        
    # 4. Process template
    with open(template_path, "r") as f:
        content = f.read()
        
    # Replace \veritas{Label} with value
    def replace_var(m):
        key = m.group(1)
        if key in data:
            return str(data[key])
        print(f"Warning: Template key '{key}' not found in exports.")
        return f"MISSING({key})"
        
    rendered = re.sub(r'\\veritas\{(.+?)\}', replace_var, content)
    
    out_tex = os.path.splitext(template_path)[0] + ".generated.tex"
    with open(out_tex, "w") as f:
        f.write(rendered)
        
    print(f"Generated LaTeX: {out_tex}")
    
    # 5. Compile PDF (Optional - check if pdflatex exists)
    import shutil
    if shutil.which("pdflatex"):
        print("[Veritas] Compiling PDF...")
        subprocess.run(["pdflatex", "-interaction=nonstopmode", out_tex], capture_output=True)
        pdf_path = out_tex.replace(".tex", ".pdf")
        if os.path.exists(pdf_path):
             print(f"Success: {pdf_path}")
        else:
             print("Error compiling PDF. Check log.")
    else:
        print("Skipping PDF generation (pdflatex not found).")

def cmd_test(args):
    print("[Veritas] Running tests...")
    
    # 1. Discover .ver tests in tests/
    test_dir = "tests"
    if os.path.exists(test_dir):
        ver_tests = [f for f in os.listdir(test_dir) if f.endswith(".ver")]
        for t in ver_tests:
            path = os.path.join(test_dir, t)
            print(f"  Veritas: {t} ... ", end="")
            try:
                with open(path, "r") as f:
                    source = f.read()
                # Determine if it SHOULD fail based on filename or content
                should_fail = "error" in t.lower() or "undefined" in t.lower()
                
                try:
                    compile_veritas(source, base_dir=test_dir)
                    if should_fail:
                        print("Fail (Unexpected success)")
                    else:
                        print("Pass")
                except Exception as e:
                    if should_fail:
                        print("Pass (Expected failure)")
                    else:
                        print(f"Fail ({e})")
            except Exception as e:
                print(f"Error reading test: {e}")

    # 2. Discover .py tests
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(test_dir, pattern='test_*.py')
    print("  Python Unit Tests:")
    runner = unittest.TextTestRunner(verbosity=1)
    runner.run(suite)

def main():
    parser = argparse.ArgumentParser(description="Veritas Language CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ... existing subparsers ...
    
    # Test
    p_test = subparsers.add_parser("test", help="Run tests")
    p_test.set_defaults(func=cmd_test)

    # Report
    p_report = subparsers.add_parser("report", help="Generate PDF report")
    p_report.add_argument("--template", default="report.vtex", help="Path to LaTeX template")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
