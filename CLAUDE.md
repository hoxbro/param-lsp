# About param-lsp

param-lsp is a Language Server Protocol (LSP) implementation for the HoloViz Param library. It provides IDE support for Python codebases that use Param, offering:

- **Autocompletion**: Context-aware completions for Param class constructors, parameter definitions, and @param.depends decorators
- **Type checking**: Real-time validation of parameter types, bounds, and constraints with error diagnostics
- **Hover information**: Rich documentation for Param parameters including types, bounds, descriptions, and default values
- **Cross-file analysis**: Intelligent parameter inheritance tracking across local and external Param classes (Panel, HoloViews, etc.)

The server analyzes Python AST to understand Param usage patterns and provides intelligent IDE features for both local Parameterized classes and external library classes like Panel widgets and HoloViews elements.

# General

- The correct environment is always activated with UV
- If you create a new file in `src/` or `tests/` use `git add --intent-to-add` for it. If you then remove the file remember to `git rm`
- Use relative import for `param_lsp` and absolute imports for tests

# New Feature

- After each new feature add a test / tests

# Changes

- Always confirm that the tests passes with `pytest tests/`
- Always confirm that lint passes with `prek run --all-files`

# param Nomenclature

## param.Parameterized

The base class that all Param-enabled classes inherit from. Classes that inherit from `Parameterized` gain the ability to declare parameters and benefit from validation, documentation, and other Param features.

Key features:

- Automatic parameter validation and type checking
- Parameter inheritance from parent classes
- Built-in `.param` namespace for parameter access and introspection
- Automatic documentation generation from parameter descriptions

Example:

```python
class MyWidget(param.Parameterized):
    width = param.Integer(default=100, bounds=(1, 1000))
    height = param.Integer(default=50, bounds=(1, 1000))
    title = param.String(default="Widget")
```

## param.Parameter

The base class for all parameter types (Number, String, Boolean, etc.). Individual parameter instances are created by subclassing Parameter and are used as class attributes on Parameterized classes.

Example:

```python
class Settings(param.Parameterized):
    threshold = param.Number(default=0.5, bounds=(0, 1), doc="Detection threshold")
    mode = param.Selector(default="auto", objects=["auto", "manual"])
```

## param.depends

The `@param.depends` decorator is used to declare dependencies between methods and parameters. When a parameter value changes, any methods decorated with `@param.depends` that depend on that parameter will be automatically triggered or invalidated.

Key usage patterns:

- `@param.depends('param_name')` - Method depends on a single parameter
- `@param.depends('param1', 'param2')` - Method depends on multiple parameters
- `@param.depends('param_name', watch=True)` - Automatically call method when parameter changes
- `@param.depends('nested.param')` - Depend on nested object parameters
- Used commonly with Panel for reactive dashboards and HoloViews for dynamic plots

Example:

```python
class MyClass(param.Parameterized):
    value = param.Number(default=1.0)

    @param.depends('value')
    def compute(self):
        return self.value * 2
```
