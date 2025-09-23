# About param-lsp

param-lsp is a Language Server Protocol (LSP) implementation for the HoloViz Param library. It provides IDE support for Python codebases that use Param, offering:

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Type checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

The server analyzes Python AST to understand Param usage patterns and provides intelligent IDE features for both local Parameterized classes and external library classes like Panel widgets and HoloViews elements.

# General

- The correct environment is always activated with UV
- If you create a new file in `src/` or `tests/` use `git add --intent-to-add` for it.
- Use relative import for `param_lsp` and absolute imports for tests

# New Feature

- After each new feature add a test / tests

# Changes

- Always confirm that the tests passes with `pytest tests/`
- Always confirm that lint passes with `prek run --all-files`
