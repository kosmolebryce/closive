"""Closures

Abstractions for callback-heavy control flows with explicit state management.
"""

from copy import copy
from collections.abc import Callable
from functools import wraps, reduce
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from .results import Result


class PipelineState:
    """Container for managing state throughout a pipeline execution."""
    
    def __init__(self, initial_value: Any = None):
        """Initialize pipeline state with an optional initial value."""
        self.current = initial_value  # Current value being passed through the pipeline
        self.history = []  # History of all intermediate values
        self.metadata = {}  # Optional metadata for each step
        
    def update(self, value: Any, step_name: str = None, **metadata) -> None:
        """Update the current value and record history."""
        # Store the previous value in history with metadata
        self.history.append({
            'value': self.current,
            'step': step_name,
            'metadata': {**metadata}
        })
        # Update the current value
        self.current = value
        
    def get_history(self) -> List[Dict]:
        """Get the full transformation history."""
        return self.history
    
    def last_n_values(self, n: int = 1) -> List[Any]:
        """Get the last n values from the history."""
        if n <= 0:
            return []
        return [step['value'] for step in self.history[-n:]]


class _Closure:
    """A callable decorator factory that supports chaining transformations with explicit state management."""

    def __init__(self, fn: Optional[Callable] = None, debug: bool = False):
        """
        Instantiates a new closure.

        Args:
          fn: 
            The function whose return value will be passed as the first argument to the next callback.
          debug:
            If True, prints each step of the transformation pipeline.
        """
        if fn is not None and not callable(fn):
            raise TypeError("Expected a callable to initialize closure.")
        
        # Default identity function if None provided
        if fn is None:
            def identity(x, *args, **kwargs): 
                return x
            fn = identity
            fn.__name__ = "identity"
        
        self._callbacks = [fn]
        self._debug = debug
        self._name = fn.__name__ if hasattr(fn, "__name__") else "unnamed"
        
        # Metadata for each callback
        self._callback_metadata = [{
            'name': self._name,
            'description': fn.__doc__ or "No description"
        }]
        
    
    def __call__(self, target):
        @wraps(target)
        def wrapped(*args, **kwargs):
            # 1) Lift initial call
            try:
                initial = target(*args, **kwargs)
                result = Result.Ok(initial)
            except Exception as e:
                result = Result.Err(e)

            # 2) Run through callbacks
            for fn, meta in zip(self._callbacks, self._callback_metadata):
                result = result.bind(lambda v, fn=fn: self._apply_step(fn, v, *args, **kwargs))
                if not result.ok:
                    break

            # 3a) If the user asked for a default, recover here
            if not result.ok and hasattr(self, "_default_on_error"):
                result = result.recover(lambda _: self._default_on_error)

            # 3b) Unwrap or raise
            if result.ok:
                return result.value
            else:
                raise result.value

        wrapped._closure = self
        return wrapped


    def unsafe(self) -> "_Closure":
        """
        Return a version of this closure that skips the monadic wrapping
        and runs in the original imperative "fail-fast" mode.
        """
        new = copy(self)
        new._use_monad = False
        return new

    def __rshift__(self, other: Union['_Closure', Callable]) -> '_Closure':
        """
        Enables chaining using the >> operator.
        Handles both _Closure instances and callables.
        """
        new = copy(self)
        
        if isinstance(other, _Closure):
            # Combine two closure pipelines
            new._callbacks.extend(other._callbacks)
            new._callback_metadata.extend(other._callback_metadata)
        elif callable(other):
            # Add a callable function to the pipeline
            new._callbacks.append(other)
            new._callback_metadata.append({
                'name': other.__name__ if hasattr(other, "__name__") else "unnamed",
                'description': other.__doc__ or "No description"
            })
        else:
            raise TypeError(f"Cannot chain with >> - expected a callable or _Closure, got {type(other).__name__}")
            
        return new

    @property
    def callbacks(self) -> List[Callable]:
        """Get the list of callbacks in the pipeline."""
        return self._callbacks
    
    @property
    def callback_info(self) -> List[Dict]:
        """Get detailed information about each callback in the pipeline."""
        return self._callback_metadata

    @callbacks.setter
    def callbacks(self, value: List[Callable]) -> None:
        """Set the callbacks list, ensuring all elements are callable."""
        if not all(callable(fn) for fn in value):
            raise TypeError("All callbacks must be callable")
        self._callbacks = value
        
        # Update metadata for each callback
        self._callback_metadata = []
        for fn in value:
            self._callback_metadata.append({
                'name': fn.__name__ if hasattr(fn, "__name__") else "unnamed",
                'description': fn.__doc__ or "No description"
            })
    
    @property
    def count(self) -> int:
        """Get the number of callbacks in the pipeline."""
        return len(self._callbacks)

    @property
    def firstcb(self) -> Optional[Callable]:
        """Get the first callback in the pipeline."""
        return self._callbacks[0] if self._callbacks else None
   
    @property
    def lastcb(self) -> Optional[Callable]:
        """Get the last callback in the pipeline."""
        return self._callbacks[-1] if self._callbacks else None
    
    def pipe(self, fn: Callable, name: str = None, description: str = None) -> "_Closure":
        """Add a callback to the pipeline with optional metadata."""
        if not callable(fn):
            raise TypeError(f"pipe expects a callable, got {type(fn).__name__}")
            
        new = copy(self)
        new._callbacks.append(fn)
        
        # Add metadata for the callback
        new._callback_metadata.append({
            'name': name or (fn.__name__ if hasattr(fn, "__name__") else "unnamed"),
            'description': description or fn.__doc__ or "No description"
        })
        
        return new

    def drain(self) -> "_Closure":
        """Remove a callback from the end of the pipeline."""
        if not self._callbacks:
            raise ValueError("Cannot drain callback from empty pipeline.")
        
        new = copy(self)
        new._callbacks.pop()
        new._callback_metadata.pop()
        return new

    def repeat(self, x: int) -> "_Closure":
        """
        Repeats the last callback x additional times.
        """
        if not self._callbacks:
            raise ValueError("No callback to repeat in empty pipeline.")
        if x < 1:
            raise ValueError(f"Repeat count must be at least 1, got {x}")
        
        new = copy(self)
        callback = new._callbacks[-1]
        metadata = new._callback_metadata[-1]
        
        for i in range(x):
            new._callbacks.append(callback)
            # Add metadata but mark as repeated
            repeated_metadata = copy(metadata)
            repeated_metadata['repeated'] = True
            repeated_metadata['repeat_index'] = i + 1
            new._callback_metadata.append(repeated_metadata)
            
        return new
    
    def trace(self, input_value, *args, **kwargs):
        result = Result.Ok(input_value)
        for idx, (fn, meta) in enumerate(zip(self._callbacks, self._callback_metadata)):
            result = result.bind(lambda v: _apply_step(fn, v, *args, **kwargs))
            yield {
                "index": idx,
                "step": meta["name"],
                "success": result.ok,
                **({"value": result.value} if result.ok else {"error": result.value})
            }
            if not result.ok:
                break
   

    @staticmethod
    def _apply_step(fn, v, *a, **kw):
        try:
            return Result.Ok(fn(v, *a, **kw))
        except Exception as e:
            return Result.Err(e)


    def visualize(self) -> str:
        """
        Generate a text representation of the pipeline.
        """
        if not self._callbacks:
            return "Empty pipeline"
        
        result = ["Pipeline:"]
        for idx, metadata in enumerate(self._callback_metadata):
            name = metadata['name']
            if idx == 0:
                result.append(f"  Input → [{name}]")
            else:
                result.append(f"        → [{name}]")
        
        return "\n".join(result)

    # Operator methods integrated into the _Closure class
    def add(self, n: Union[int, float]) -> "_Closure":
        """Add a function that adds n to its input value."""
        def inner(r, *args, **kwargs):
            return r + n
        inner.__name__ = f"add({n})"
        inner.__doc__ = f"Add {n} to the input value"
        return self.pipe(inner)

    def subtract(self, n: Union[int, float]) -> "_Closure":
        """Add a function that subtracts n from its input value."""
        def inner(r, *args, **kwargs):
            return r - n
        inner.__name__ = f"subtract({n})"
        inner.__doc__ = f"Subtract {n} from the input value"
        return self.pipe(inner)

    def multiply(self, n: Union[int, float]) -> "_Closure":
        """Add a function that multiplies its input value by n."""
        def inner(r, *args, **kwargs):
            return r * n
        inner.__name__ = f"multiply({n})"
        inner.__doc__ = f"Multiply the input value by {n}"
        return self.pipe(inner)

    def divide(self, n: Union[int, float]) -> "_Closure":
        """Add a function that divides its input value by n."""
        if n == 0:
            raise ValueError("Cannot divide by zero")
        def inner(r, *args, **kwargs):
            return r / n
        inner.__name__ = f"divide({n})"
        inner.__doc__ = f"Divide the input value by {n}"
        return self.pipe(inner)

    def exponentiate(self, n: Union[int, float]) -> "_Closure":
        """Add a function that raises its input value to the power of n."""
        def inner(r, *args, **kwargs):
            return r ** n
        inner.__name__ = f"exponentiate({n})"
        inner.__doc__ = f"Raise the input value to the power of {n}"
        return self.pipe(inner)

    def square(self) -> "_Closure":
        """Add a function that squares the input value."""
        def square_fn(r, *args, **kwargs):
            return r ** 2
        square_fn.__name__ = "square"
        square_fn.__doc__ = "Square the input value"
        return self.pipe(square_fn)

    def cube(self) -> "_Closure":
        """Add a function that cubes the input value."""
        def cube_fn(r, *args, **kwargs):
            return r ** 3
        cube_fn.__name__ = "cube"
        cube_fn.__doc__ = "Cube the input value"
        return self.pipe(cube_fn)

    def squareroot(self) -> "_Closure":
        """Add a function that returns the square root of the input value."""
        def sqrt_fn(r, *args, **kwargs):
            if r < 0:
                raise ValueError(f"Cannot compute square root of negative number: {r}")
            return r ** (1/2)
        sqrt_fn.__name__ = "squareroot"
        sqrt_fn.__doc__ = "Calculate the square root of the input value"
        return self.pipe(sqrt_fn)
    
    def cuberoot(self) -> "_Closure":
        """Add a function that returns the cube root of the input value."""
        def cbrt_fn(r, *args, **kwargs):
            return r ** (1/3)
        cbrt_fn.__name__ = "cuberoot"
        cbrt_fn.__doc__ = "Calculate the cube root of the input value"
        return self.pipe(cbrt_fn)

    def root(self, n: Union[int, float]) -> "_Closure":
        """Add a function that returns the nth root of its input value."""
        if n == 0:
            raise ValueError("Cannot compute 0th root")
        def root_fn(r, *args, **kwargs):
            if n % 2 == 0 and r < 0:
                raise ValueError(f"Cannot compute even root ({n}) of negative number: {r}")
            return r ** (1/n)
        root_fn.__name__ = f"root({n})"
        root_fn.__doc__ = f"Calculate the {n}th root of the input value"
        return self.pipe(root_fn)


    def map(self, fn: Callable[[Any], Any], *,
                    name: str = None, description: str = None) -> "_Closure":
        """
        Apply `fn` to each element of the current value (which must be iterable).
        """
        def mapper(coll, *args, **kwargs):
            try:
                return [fn(x) for x in coll]
            except TypeError:
                raise TypeError(f"map expects an iterable, got {type(coll).__name__}")
        mapper.__name__ = name or f"map({fn.__name__})"
        mapper.__doc__ = description or f"Map {fn.__name__} over iterable"
        return self.pipe(mapper)

    def filter(self, predicate: Callable[[Any], bool], *,
                        name: str = None, description: str = None) -> "_Closure":
        """
        Keep only those elements `x` for which `predicate(x)` is truthy.
        """
        def fil(coll, *args, **kwargs):
            try:
                return [x for x in coll if predicate(x)]
            except TypeError:
                raise TypeError(f"filter expects an iterable, got {type(coll).__name__}")
        fil.__name__ = name or f"filter({predicate.__name__})"
        fil.__doc__ = description or f"Filter iterable by {predicate.__name__}"
        return self.pipe(fil)

    def fold(self, fn: Callable[[Any, Any], Any], initial: Any, *,
                    name: str = None, description: str = None) -> "_Closure":
        """
        Reduce the current iterable by applying `fn(acc, x)` across all elements, 
        starting from `initial`.
        """
        def fld(coll, *args, **kwargs):
            try:
                return reduce(fn, coll, initial)
            except TypeError:
                raise TypeError(f"fold expects an iterable, got {type(coll).__name__}")
        fld.__name__ = name or f"fold({fn.__name__}, init={initial!r})"
        fld.__doc__ = description or f"Fold iterable with {fn.__name__}, init={initial!r}"
        return self.pipe(fld)


    # Iterator for pipeline introspection
    def __iter__(self) -> Generator[Tuple[int, Callable, Dict], None, None]:
        """
        Iterate through the pipeline steps, yielding (index, callback, metadata) tuples.
        """
        for idx, (callback, metadata) in enumerate(zip(self._callbacks, self._callback_metadata)):
            yield idx, callback, metadata
    
    # Accessing intermediate results
    def inspect(self, input_value: Any, *args, **kwargs) -> Dict:
        """
        Run the pipeline with the given input and return a detailed report.
        """
        results = list(self.trace(input_value, *args, **kwargs))
        
        if not results:
            return {'success': False, 'error': 'Empty pipeline'}
        
        # Check if pipeline completed successfully
        success = all(step.get('success', False) for step in results[1:])
        
        return {
            'input': input_value,
            'output': results[-1]['value'] if success else None,
            'steps': results,
            'success': success,
            'step_count': len(results) - 1  # Don't count input
        }

    def recover(self, handler: Callable[[Any], Any],
                        *, name=None, description=None) -> "_Closure":
        def inner(v, *a, **kw):
            # `v` here is *always* a Result[T,E]
            return v.recover(handler)
        inner.__name__ = name or "recover"
        inner.__doc__ = description or "Recover from an error via handler"
        return self.pipe(inner)

    def unwrap_or(self, default, *, name=None, description=None):
        def inner(v, *a, **kw):
            return v.unwrap_or(default)
        inner.__name__ = name or f"unwrap_or({default!r})"
        inner.__doc__ = description or "Provide a default on error"
        return self.pipe(inner)

    def get_step_result(self, input_value: Any, step_idx: int, *args, **kwargs) -> Any:
        """
        Execute the pipeline up to the specified step and return its result.
        
        Args:
            input_value: The input value to the pipeline
            step_idx: Index of the step (0-based) to get the result of
            
        Returns:
            The result of the specified step
        """
        if step_idx < 0 or step_idx >= len(self._callbacks):
            raise IndexError(f"Step index {step_idx} out of range (0-{len(self._callbacks)-1})")
            
        # If first step requested, just call it directly
        if step_idx == 0:
            return self._callbacks[0](input_value, *args, **kwargs)
            
        # Otherwise run the pipeline up to that step
        value = input_value
        for i in range(step_idx + 1):
            value = self._callbacks[i](value, *args, **kwargs)
        
        return value
    
    # Magic method to support function composition with @
    def __matmul__(self, other: '_Closure') -> '_Closure':
        """
        Support function composition with the @ operator.
        f @ g is equivalent to g(f(x))
        """
        # Here, 'other' is the function to be applied first
        if not isinstance(other, _Closure):
            raise TypeError(f"Expected _Closure, got {type(other).__name__}")
            
        result = copy(other)
        for cb, meta in zip(self._callbacks, self._callback_metadata):
            result._callbacks.append(cb)
            result._callback_metadata.append(meta)
            
        return result
    
    
    def __or__(self, default_value):
        new = copy(self)
        new._default_on_error = default_value
        return new


    # Aliases for a more expressive API
    do = next = then = pipe
    re = redo = rept = repeat


# Main public API
def closure(fn: Optional[Callable] = None, debug: bool = False) -> _Closure:
    """Create a closure. 
    
    This is a factory function for creating a new closure pipeline.

    Args:
      fn: 
        The first transformation function in the pipeline.
      debug:
        Optional flag to enable debug prints.

    Returns:
      A _Closure instance wrapping the initial function.
    """
    return _Closure(fn, debug=debug)


# Standalone transformation functions (for compatibility)
def add(n):
    """Returns a function that adds n to its input value."""
    def inner(r, *args, **kwargs):
        return r + n
    inner.__name__ = f"add({n})"
    inner.__doc__ = f"Add {n} to the input value"
    return inner

def subtract(n):
    """Returns a function that subtracts n from its input value."""
    def inner(r, *args, **kwargs):
        return r - n
    inner.__name__ = f"subtract({n})"
    inner.__doc__ = f"Subtract {n} from the input value"
    return inner

def multiply(n):
    """Returns a function that multiplies its input value by n."""
    def inner(r, *args, **kwargs):
        return r * n
    inner.__name__ = f"multiply({n})"
    inner.__doc__ = f"Multiply the input value by {n}"
    return inner

def divide(n):
    """Returns a function that divides its input value by n."""
    if n == 0:
        raise ValueError("Cannot divide by zero")
    def inner(r, *args, **kwargs):
        return r / n
    inner.__name__ = f"divide({n})"
    inner.__doc__ = f"Divide the input value by {n}"
    return inner

def exponentiate(n):
    """Returns a function that raises its input value to the power of n."""
    def inner(r, *args, **kwargs):
        return r ** n
    inner.__name__ = f"exponentiate({n})"
    inner.__doc__ = f"Raise the input value to the power of {n}"
    return inner

def square(r, *args, **kwargs):
    """Returns the square of the input value."""
    return r ** 2

def cube(r, *args, **kwargs):
    """Returns the cube of the input value."""
    return r ** 3

def squareroot(r, *args, **kwargs):
    """Returns the square root of the input value."""
    if r < 0:
        raise ValueError(f"Cannot compute square root of negative number: {r}")
    return r ** (1/2)
    
def cuberoot(r, *args, **kwargs):
    """Returns the cube root of the input value."""
    return r ** (1/3)

def root(n):
    """Returns a function that returns the nth root of its input value."""
    if n == 0:
        raise ValueError("Cannot compute 0th root")
    def inner(r, *args, **kwargs):
        if n % 2 == 0 and r < 0:
            raise ValueError(f"Cannot compute even root ({n}) of negative number: {r}")
        return r ** (1/n)
    inner.__name__ = f"root({n})"
    inner.__doc__ = f"Calculate the {n}th root of the input value"
    return inner

def linfunc(params, *args, **kwargs):
    """Uses the provided linear parameters to process x.

    Args:
      params:
        A tuple containing (x, m, b) where:
        x: A list-like object containing a series of x values.
        m: A float or integer that represents the slope of the line.
        b: A float or integer that represents the line's y-intercept.
    """
    try:
        import pandas as pd
        import numpy as np
    except Exception as e:
        raise ImportError("Required libraries missing: pandas, numpy") from e

    if not params or len(params) < 3:
        raise ValueError("params must contain at least (x, m, b)")
        
    x, m, b = params[0:3]
    
    print("m = {}".format(m))
    print("x = {}".format(x))
    print("b = {}".format(b))
    
    try:
        y = np.array([(m * n + b) for n in x])
        df = pd.DataFrame({"x": x, "y": y})
    except Exception as e:
        raise ValueError(f"Error computing linear function: {e}")
    
    return df


# Visualization method
def linvis(df, *args, **kwargs):
    """Creates a linear visualization from a DataFrame with x and y columns.
    
    Returns:
        A seaborn.objects.Plot object.
    """
    try:
        import seaborn as sns
        import seaborn.objects as so
    except Exception as e:
        raise ImportError("Required library missing: seaborn") from e
    
    if 'x' not in df.columns or 'y' not in df.columns:
        raise ValueError("DataFrame must contain 'x' and 'y' columns")
    
    sns.set_palette("magma")
    
    try:
        p = (
            so.Plot(data=df, x="x", y="y")
            .add(so.Line())
            .label(title="y = mx + b")
            .theme({
                "figure.dpi": 300,
                "font.family": "sans-serif"
            })
        )
        return p
    except Exception as e:
        raise ValueError(f"Error creating visualization: {e}") from e


def to_dataframe(r, *args, **kwargs) -> tuple:
    """Converts the pipeline result and original input to a DataFrame.

    Creates a DataFrame with two columns:
    - "input": The original input values passed to the function.
    - "output": The transformed values after all pipeline operations.
    
    Args:
      r:
        The result from the pipeline (transformed values).
      *args:
        Arguments passed to the decorated function. First arg is used
        as input.
      **kwargs:
        Keyword arguments passed to the decorated function.
    
    Returns:
        pandas.DataFrame: A DataFrame with "input" and "output" columns.
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError as e:
        raise ImportError("Required libraries missing: pandas, numpy") from e
    
    if not args:
        raise ValueError("No input values found in args")
    
    input_val = args[0]  # Get the first argument passed to the decorated function
    
    # Handle different input types
    if isinstance(input_val, (list, tuple, np.ndarray)) and not isinstance(r, (list, tuple, np.ndarray)):
        # If input was array-like but output is scalar, we need to apply the transformation
        # to each element to get the corresponding outputs
        raise ValueError(
            "Cannot create DataFrame: array-like input resulted in scalar output. "
            "The transformation might not preserve the array structure."
        )
    
    # Create the DataFrame based on input and result types
    if isinstance(input_val, (list, tuple, np.ndarray)) and isinstance(r, (list, tuple, np.ndarray)):
        # Both input and output are array-like
        if len(input_val) != len(r):
            raise ValueError(
                f"Input and output arrays have different lengths: {len(input_val)} vs {len(r)}"
            )
        df = pd.DataFrame({
            "input": input_val,
            "output": r
        })
    else:
        # Scalar input and output
        df = pd.DataFrame({
            "input": np.array([input_val]),
            "output": np.array([r])
        })
    
    return args[0], df

def to_plot(r, *args, **kwargs) -> "_Closure":
    """Plot the data resulted by a transformation pipeline.
    
    Creates a seaborn plot from a univariate data frame (such as that
    returned by the `to_dataframe` method or the standalone `dataframe`
    function, both of which return a two-column data frame comprising
    the pipeline's input and output values.

    Args:
      r:
        The result of the last callback in the pipeline.
      *args:
        Arguments passed to the decorated function.
        Unused here but included to preserve pipeline sanity.
      **kwargs:
        Keyword arguments passed to the decorated function.
        Unused here but included to preserve pipeline sanity.
    
    Returns:
        A tuple containing r (unchanged), along with a seaborn.Plot
        object and the pandas.DataFrame object from which it derived,
        in that order.
    """
    try:
        import seaborn as sns
        import seaborn.objects as so
    except ImportError as e:
        raise ImportError(
            "Closive could not import seaborn. Please install it "
            "via `pip install seaborn`."
        )
    else:
        sns.set_palette("magma")

    # Extract the results tuple into separate objects
    result, df = r

    minx = min(df["input"]) - 1
    maxx = max(df["input"]) + 1
    miny = min(df["output"]) - 1
    maxy = max(df["output"]) + 1

    p = (
        so.Plot(data=df, x="input", y="output")
        .add(so.Line())
        .label(title="Results", x="Input", y="Output")
        .theme({
            "axes.edgecolor": "black",
            "axes.facecolor": "white",
            "axes.grid": True,
            "axes.labelsize": 10,
            "axes.labelweight": "bold",
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "figure.dpi": 200,
            "font.family": "monospace",
            "font.size": 9,
            "grid.color": "lightgray",
            "grid.linestyle": "--"
        })
        .layout(size=(6, 4))
        .limit(x=(minx, maxx), y=(miny, maxy))
    )

    return result, p, df

def _closure_to_plot(self):
    """Add a Seaborn Plot creation operation to the pipeline."""
    return self.pipe(to_plot)

def _closure_to_dataframe(self):
    """Add a DataFrame creation operation to the pipeline."""
    return self.pipe(to_dataframe)


# Standalone functions to be used with the >> operator.
def dataframe(r, *args, **kwargs):
    """Standalone function to convert pipeline results to a DataFrame."""
    return to_dataframe(r, *args, **kwargs)

def plot(r, *args, **kwargs):
    """Standalone function to convert results to a seaborn.Plot."""
    return to_plot(r, *args, **kwargs)
    

# Add method to create a linfunc closure
def _closure_linfunc(self):
    """Add a linear function operation to the pipeline."""
    return self.pipe(linfunc)

# Add method to create a linvis closure
def _closure_linvis(self):
    """Add a visualization operation to the pipeline."""
    return self.pipe(linvis)

# Add the methods to the _Closure class
_Closure.linfunc = _closure_linfunc
_Closure.linvis = _closure_linvis
_Closure.to_dataframe = _closure_to_dataframe
_Closure.to_plot = _closure_to_plot

# Pre-composed pipeline
linplot = closure(linfunc) >> linvis

if __name__ == "__main__":
    # Example usage with the improved pipeline
    pipeline = closure(lambda x: x + 1, debug=True).square().multiply(2).add(3)
    
    # Use as a decorator
    @pipeline
    def calculate(x):
        return x
    
    result = calculate(5)
    print(f"Final result: {result}")
    
    # Demonstrate pipeline introspection
    print("\nPipeline visualization:")
    print(pipeline.visualize())
    
    # Inspect the pipeline execution
    print("\nInspection report:")
    report = pipeline.inspect(5)
    for step in report['steps']:
        if 'value' in step:
            print(f"Step {step['index']} ({step['step']}): {step['value']}")
    
    # Get result at specific step
    third_step = pipeline.get_step_result(5, 2)
    print(f"\nResult after third step: {third_step}")
    
    # Tracing through execution
    print("\nTracing execution:")
    for step in pipeline.trace(5):
        if 'success' in step and step['success']:
            print(f"{step['step']}: {step['value']}")
        elif 'error' in step:
            print(f"{step['step']}: ERROR - {step['error']}")
