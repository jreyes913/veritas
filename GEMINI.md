# Veritas Language Mandates

## 1. Reliability First
- All compiler changes MUST preserve source span tracking (line numbers).
- Errors MUST be reported with clear messages and context.
- The `veritas` CLI is the single source of truth for building, testing, and reporting.

## 2. Engineering Integrity
- Dimensional analysis is MANDATORY for engineering calculations.
- Avoid introducing implicit conversions that lose unit information.
- Zero-cost abstractions: Units are erased at runtime; C performance must not be compromised.

## 3. Literate Programming
- Code and documentation (reports) should be tightly coupled.
- `Export` statements ensure data consistency between simulation and report.

## Project Structure
- `compiler/`: Modularized compiler pipeline.
- `src/`: Veritas source files.
- `tests/`: Project tests (Python unit tests and Veritas integration tests).
- `veritas.toml`: Project manifest.

## CLI Usage
- `veritas new <name>`: Create new project.
- `veritas build`: Compile to C and binary.
- `veritas run`: Compile and execute.
- `veritas test`: Run unit and integration tests.
- `veritas report [--template T]`: Generate PDF report from exports.
