# Closive  
_Data Transformatics for Python_

Closive is a focussed toolkit that elevates a chain of ordinary Python call-backs into an explicit, inspectable, serialisable _pipeline_.  
Each step is a plain callable; every intermediate value is wrapped in a `Success` or `Failure` from `returns.result`; and the entire chain is a first-class object that can be traced, visualised, re-combined, or persisted.

> A pipeline is to callbacks what a module is to functions: a durable unit of composition, documentation, and reuse.

---

## Table of Contents
1. Installation  
2. Quick Start  
3. Architecture & Core Abstractions  
   3.1 Closure Pipeline  
   3.2 Result Monad Integration  
   3.3 Commutator  
4. Introspection & Debugging  
5. Error Handling Patterns  
6. Collection Utilities  
7. DataFrame & Plot Helpers  
8. External Pipelines (YAML)  
9. Extending Closive  
10. Contributing  
11. License  

---

## 1 Installation

Closive is published on PyPI and supports Python 3.9 or later.

```bash
pip install closive
```

Optional extras for data-centric helpers:

```bash
pip install pandas numpy seaborn
```

---

## 2 Quick Start

```python
from closive import closure, add, multiply, square

# 1. Construct a pipeline.
calc = (
    closure(lambda x: x + 1)   # seed
    >> multiply(3)             # step 1
    >> square                  # step 2
    >> add(5)                  # step 3
)

# 2. Execute like an ordinary function.
calc(2)
# → 50

# 3. Inspect the full run.
print(calc.explain(2))
```

Console output:

```
00 ✓ <lambda>      → 3
01 ✓ multiply(3)   → 9
02 ✓ square        → 81
03 ✓ add(5)        → 86
```

---

## 3 Architecture & Core Abstractions

### 3.1 Closure Pipeline

`closure(fn=None, *, debug=False) → _Pipeline`  

* If `fn` is omitted the pipeline begins with the identity step.  
* Append additional steps with the right-shift operator `>>`.  
* The pipeline itself is callable; the first positional argument forms the initial value and any further `*args`/`**kwargs` are forwarded to _every_ step in the chain.

```python
pipeline = closure() >> square >> add(7)
result   = pipeline(4)          # → 23
```

### 3.2 Result Monad Integration

Internal execution is performed in terms of `returns.result.Result`:

* `Success(value)` represents normal flow.  
* `Failure(exc)` represents an exception captured as data.  

Closive automatically:

1. Wraps raw outputs into `Success`.  
2. Short-circuits on the first `Failure` not otherwise handled.  
3. Provides functional helpers (`map`, `bind`, `alt`, `lash`) for direct Result manipulation.

### 3.3 Commutator

A commutator is a pass-through helper that performs a side effect yet returns the input value unchanged.  
Closive ships several ready-made instances.

```python
from closive import tap, log, identity, noop

peek  = tap(print)    # send value to stdout
audit = log()         # log at INFO
```

A commutator is inserted exactly like any other step:

```python
pipeline = closure() >> tap(lambda x: print("•", x)) >> square
```

Provided commutators:

| Name          | Purpose                               |
|---------------|---------------------------------------|
| `identity`    | Return the value unchanged.           |
| `noop`        | Produce `None` irrespective of input. |
| `tap(fn)`     | Execute `fn(value)`, then forward.    |
| `log(...)`    | Log the value, then forward.          |
| `as_tuple`    | Return `(x, x)`.                      |
| `ignore_return`| Synonym for `identity`.              |

---

## 4 Introspection & Debugging

Closive treats the pipeline as data and therefore supplies multiple inspection surfaces.

| Method                                  | Result & Notes                                                                        |
|-----------------------------------------|---------------------------------------------------------------------------------------|
| `visualize()`                           | ASCII diagram of the pipeline topology.                                               |
| `trace(value)`                          | Generator of per-step event dictionaries.                                             |
| `explain(value, *, show_values=True)`   | Pretty, colourised, step-by-step report, also renders rich HTML in Jupyter.           |
| `inspect(value)`                        | JSON-serialisable dict containing input, output, per-step success, and metadata.      |
| `get_step_result(value, index)`         | Execute up to `index` and return the intermediate result, raising on Failure.         |
| `_Pipeline(debug=True)`                 | Immediate `print` of step names during execution.                                     |

---

## 5 Error Handling Patterns

Closive treats exceptions as values and lets you declare remediation strategies.

### 5.1 Static Fallback

```python
safe = closure() >> divide(0) | 0    # ‘0’ returned on ZeroDivisionError
```

Operator `|` substitutes a static value and terminates the chain.

### 5.2 Dynamic Handler

```python
def substitute(exc):
    return f"handled: {exc}"

recover = (
    closure()
    >> risky_op
    .handle_error(
        handler=substitute,
        continue_pipeline=True,       # execute remaining steps
        preserve_context=False        # ignore original exception afterwards
    )
)
```

`handle_error` parameters:

| Name                | Type                         | Meaning                                                    |
|---------------------|------------------------------|------------------------------------------------------------|
| `fallback`          | `Any`                        | Static replacement value.                                  |
| `handler`           | `Callable[[Exception], Any]` | Dynamic replacement; takes precedence over `fallback`.     |
| `continue_pipeline` | `bool`                       | If True, subsequent steps continue after replacement.      |
| `preserve_context`  | `bool`                       | If True, replacement value returned as `(value, exc)`.     |
| `for_errors`        | `Sequence[type[Exception]]`  | Only handle listed error types.                            |
| `propagate_others`  | `bool`                       | Re-raise non-listed exceptions when `for_errors` is used.  |

---

## 6 Collection Utilities

The pipeline offers declarative operators that expect an iterable at runtime.

```python
from closive import closure

stats = (
    closure()
    .map(lambda x: x ** 2)                   # element-wise
    .filter(lambda x: x % 2 == 0)            # keep even
    .fold(lambda acc, x: acc + x, 0)         # reduce to sum
)

stats([1, 2, 3, 4, 5])   # → 20
```

Additional structural helpers:

* `repeat(n)` – append the last step *n* additional times.  
* `drain()`  – remove the last step.

---

## 7 DataFrame & Plot Helpers

If `pandas`, `numpy`, and `seaborn` are present, Closive exposes helpers that turn numerical pipelines into tabular and graphical artefacts.

### 7.1 Linear Function & Plot

```python
from closive import closure, linfunc, linplot

params = ([0, 1, 2, 3, 4], 2, 1)  # x-values, slope m, intercept b

p = closure(linfunc) >> linplot
plot = p(params)                  # seaborn.objects.Plot
plot.show()
```

### 7.2 Generic to DataFrame / Plot

```python
from closive import closure, to_dataframe, to_plot

pipeline = closure() >> square >> to_dataframe >> to_plot
result, seaborn_plot, df = pipeline([0, 1, 2])
```

Return value is a triple so you can access whichever artefact you need.

---

## 8 External Pipelines (YAML Configuration)

Closive can materialise pipelines described in a YAML file at import time.

* Path: `~/.local/share/closive/pipelines.yml`  
* Each top-level key becomes an attribute on the imported `closive` module.  
* The file is auto-generated with an illustrative example on first run.

Example entry:

```yaml
square_plus_five:
  description: Square input then add five
  steps:
    - {module: closive.closures, function: square}
    - {module: closive.closures, function: add, args: [5]}
```

Programmatic helpers:

```python
from closive import save_pipeline, reload_pipelines

save_pipeline("square_plus_five", pipeline, "Reusable default chain")
reload_pipelines()    # dynamically adds closive.square_plus_five
```

---

## 9 Extending Closive

### 9.1 Custom Result-Aware Step

```python
from closive.closures import expects
from returns.result   import Success, Failure

@expects
def capped(max_value):
    def inner(result, *a, **k):
        return result.bind(
            lambda x: Success(x) if x <= max_value
            else Failure(ValueError(f"{x} exceeds {max_value}"))
        )
    inner.__name__ = f"capped({max_value})"
    return inner
```

Usage:

```python
pipeline = closure() >> capped(10)
```

### 9.2 Augmenting `_Pipeline`

Because `_Pipeline` is an ordinary Python class, project-specific conveniences can be added dynamically.

```python
def normalise(self):
    return self.map(lambda v: (v - min(v)) / (max(v) - min(v)))

from closive.closures import _Pipeline
_Pipeline.normalise = normalise
```

---

## 10 Contributing

Bug reports, feature proposals, and pull requests are welcome.

```bash
git clone https://github.com/kosmolebryce/closive
cd closive
pip install -r dev-requirements.txt
pytest
```

Contribution guidelines:

* Follow [Google Python Style Guide].  
* Public APIs must include docstrings and unit tests.  
* Commit messages should be imperative and scoped, e.g. “Add trace summariser”.

---

## 11 License

Closive is distributed under the MIT License.  
See the `LICENSE` file for the full legal text.

---

© 2025 K. LeBryce. All rights reserved.