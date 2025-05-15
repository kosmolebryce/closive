"""Closures

Abstractions for callback-heavy control flows with explicit state management.
Built on top of returns.result for robust Result monad implementation.
"""

from copy import copy
from collections import deque
from collections.abc import Callable
from functools import wraps, reduce
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Generic,
    Union,
    cast
)

# Import returns.result instead of custom Result implementation
from returns.result import Result, Success, Failure
from returns.pipeline import pipe
from returns.pointfree import bind, map_, alt, lash

from .jit import PipelineOptimizer, optimize

# Type variables for generic typing
A = TypeVar('A')
B = TypeVar('B')
E = TypeVar('E', bound=Exception)

class PipelineState:
    """Container for managing state throughout a pipeline execution."""
    
    def __init__(self, initial_value=None, *, size=None):
        self.current = initial_value
        # list  = unlimited;  deque = bounded;  None = disabled
        if size is None:
            self.history = []           # unlimited (old behaviour)
        elif size == 0:
            self.history = None         # no history
        else:
            self.history = deque(maxlen=size)


    def update(self, value: Any, step_name: Optional[str] = None, **metadata) -> None:
        """Update the current value and record history."""
        if self.history is not None:
            self.history.append({
                'value': self.current,
                'step': step_name,
                'metadata': {**metadata}
            })
        self.current = value
        
    def get_history(self) -> List[Dict]:
        """Get the full transformation history."""
        return self.history
    
    def last_n_values(self, n: int = 1) -> List[Any]:
        """Get the last n values from the history."""
        if n <= 0:
            return []
        return [step['value'] for step in self.history[-n:]]


class _Closure(Generic[A, B, E]):
    """
    A callable decorator factory that supports chaining transformations
    with explicit state management.
    """

    def __init__(
        self,
        fn: Optional[Callable] = None,
        debug: bool = False,
        strict: bool = True
    ) -> None:
        """
        Instantiates a new closure.

        Args:
          fn: 
            The function whose return value will be passed as the first
            argument to the next callback.
          debug:
            If True, prints each step of the transformation pipeline.
          strict:
            If True, raises all exceptions at each step in the pipeline.
        """
        if fn is not None and not callable(fn):
            raise TypeError("Expected a callable to initialize closure.")
        
        # Default identity function if None provided
        if fn is None:
            def identity(x: Any, *args: Any, **kwargs: Any) -> Any: 
                return x
            fn = identity
            fn.__name__ = "identity"
        
        self._callbacks = [fn]
        self._name = fn.__name__ if hasattr(fn, "__name__") else "unnamed"
        self._debug = debug
        self._strict = strict
        
        # Metadata for each callback
        self._callback_metadata = [{
            'name': self._name,
            'description': fn.__doc__ or "No description"
        }]
        
        # Configuration for error handling
        self._error_handler = None
        self._default_on_error = None
        self._continue_after_fallback = False
        self._preserve_error_context = False
        self._handled_error_types = None
        self._propagate_other_errors = True
   

    def __call__(self, target: Callable) -> Callable:
        @wraps(target)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            # 1) Run the initial function and wrap in Result
            try:
                initial = target(*args, **kwargs)
                result = Success(initial)
            except Exception as e:
                result = Failure(e)

            # 2) Process through the pipeline
            for idx, (fn, meta) in enumerate(zip(self._callbacks, self._callback_metadata)):
                if self._debug:
                    print(f"Step {idx}: {meta['name']}")
                
                # Process the current step
                try:
                    # For functions that expect a Result, pass it directly
                    if getattr(fn, '_expects_result', False):
                        next_result = fn(result, *args, **kwargs)
                    else:
                        # For regular functions, unwrap the Success value
                        if isinstance(result, Success):
                            # Explicitly catch exceptions from the function
                            try:
                                next_value = fn(result.unwrap(), *args, **kwargs)
                                next_result = Success(next_value)
                            except Exception as e:
                                next_result = Failure(e)
                        else:  # It's a Failure
                            next_result = result
                except Exception as e:
                    next_result = Failure(e)
                
                # Apply error handling if needed
                if isinstance(next_result, Failure):
                    handled_result, applied_fallback = self._apply_error_handling(next_result)
                    if applied_fallback:
                        if self._continue_after_fallback:
                            # Continue with the fallback value
                            result = handled_result
                        else:
                            # Stop processing and return the fallback
                            return handled_result.unwrap()
                    else:
                        # No fallback applied, use the error result
                        result = next_result
                else:
                    # No error, use the successful result
                    result = next_result
            
            # 3) Final unwrap
            if isinstance(result, Success):
                return result.unwrap()
            else:
                # Apply final fallback if available
                result, applied_fallback = self._apply_error_handling(result)
                if applied_fallback:
                    return result.unwrap()
                else:
                    raise result.failure()

        wrapped._closure = self
        return wrapped

    
    def _apply_error_handling(self, result: Result) -> Tuple[Result, bool]:
        """Apply configured error handling to a Result object."""
        if isinstance(result, Success):
            return result, False
        
        error = result.failure()
        applied_fallback = False
        
        # Check if we should handle this error type
        if self._handled_error_types is not None and not isinstance(error, self._handled_error_types):
            if self._propagate_other_errors:
                return result, False
        
        # Apply dynamic handler if available (has precedence)
        if self._error_handler is not None:
            try:
                if self._preserve_error_context:
                    # Store the original error
                    handler_result = self._error_handler(error)
                    return Success((handler_result, error)), True
                else:
                    return Success(self._error_handler(error)), True
            except Exception as handler_error:
                # If handler fails, fall back to static value
                if self._default_on_error is not None:
                    return Success(self._default_on_error), True
                else:
                    return Failure(handler_error), False
        
        # Apply static fallback if no handler or handler failed
        elif self._default_on_error is not None:
            if self._preserve_error_context:
                return Success((self._default_on_error, error)), True
            else:
                return Success(self._default_on_error), True
        
        return result, False

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
        """Repeats the last callback x additional times."""
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


    def __add__(self, other: Union['_Closure', Callable]) -> '_Closure':
        """
        Enables chaining using the + operator.
        Higher precedence than | for better composition.
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
            raise TypeError(f"Cannot chain with + - expected a callable or _Closure, got {type(other).__name__}")
                
        return new


    def handle_error(self, fallback=None, handler=None, continue_pipeline=False, 
                 preserve_context=False, for_errors=None, propagate_others=True) -> "_Closure":
        """
        Unified error handling method that consolidates multiple approaches.
        
        Args:
            fallback: Static fallback value to use when an error occurs
            handler: Function that takes an exception and returns a replacement value,
                    has higher precedence than fallback if both are provided
            continue_pipeline: If True, continue executing transformations after applying 
                            the fallback. If False, return the fallback immediately.
            preserve_context: If True, the original error is preserved in a tuple 
                            (fallback_value, original_error)
            for_errors: List of exception types to handle. If None, handle all exceptions.
            propagate_others: If True and for_errors is specified, exceptions not in 
                            for_errors will be propagated (re-raised).
        
        Returns:
            A new _Closure with error handling configured
        """
        new = copy(self)
        
        # Store error handling configuration
        if fallback is not None:
            new._default_on_error = fallback
        
        # Error handler has precedence over static fallback
        if handler is not None:
            new._error_handler = handler
        
        # Store other configuration
        new._continue_after_fallback = continue_pipeline
        new._preserve_error_context = preserve_context
        
        # Store error type filtering
        if for_errors is not None:
            if not isinstance(for_errors, (list, tuple)):
                for_errors = [for_errors]
            new._handled_error_types = tuple(for_errors)
        else:
            new._handled_error_types = None
        
        new._propagate_other_errors = propagate_others
        
        return new

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

    def trace(self, input_value, *args, **kwargs):
        """
        Traces execution through the pipeline, yielding step information.
        """
        result = Success(input_value)
        for idx, (fn, meta) in enumerate(zip(self._callbacks, self._callback_metadata)):
            # Process the current step
            try:
                # For functions that expect a Result, pass it directly
                if getattr(fn, '_expects_result', False):
                    next_result = fn(result, *args, **kwargs)
                else:
                    # For regular functions, unwrap the Result value and wrap the output
                    if isinstance(result, Success):
                        next_value = fn(result.unwrap(), *args, **kwargs)
                        # Auto-wrap plain values into Success
                        if not isinstance(next_value, (Success, Failure)):
                            next_result = Success(next_value)
                        else:
                            next_result = next_value
                    else:  # It's a Failure
                        next_result = result
            except Exception as e:
                next_result = Failure(e)
            
            result = next_result
            
            # Yield step information
            if isinstance(result, Success):
                yield {
                    "index": idx,
                    "step": meta["name"],
                    "success": True,
                    "value": result.unwrap()
                }
            else:
                yield {
                    "index": idx,
                    "step": meta["name"],
                    "success": False,
                    "error": result.failure()
                }
                break

    def visualize(self) -> str:
        """Generate a text representation of the pipeline."""
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

    def inspect(self, input_value: Any, *args, **kwargs) -> Dict:
        """Run the pipeline with the given input and return a detailed report."""
        results = list(self.trace(input_value, *args, **kwargs))
        
        if not results:
            return {'success': False, 'error': 'Empty pipeline'}
        
        # Check if pipeline completed successfully
        success = all(step.get('success', False) for step in results)
        
        last_result = results[-1]
        output = last_result.get('value') if last_result.get('success', False) else None
        
        return {
            'input': input_value,
            'output': output,
            'steps': results,
            'success': success,
            'step_count': len(results)
        }

    def get_step_result(self, input_value: Any, step_idx: int, *args, **kwargs) -> Any:
        """
        Execute the pipeline up to the specified step and return its result.
        """
        if step_idx < 0 or step_idx >= len(self._callbacks):
            raise IndexError(f"Step index {step_idx} out of range (0-{len(self._callbacks)-1})")
            
        # Run through the pipeline up to the specified step
        result = Success(input_value)
        
        for i in range(step_idx + 1):
            fn = self._callbacks[i]
            
            try:
                if getattr(fn, '_expects_result', False):
                    result = fn(result, *args, **kwargs)
                else:
                    if isinstance(result, Success):
                        value = fn(result.unwrap(), *args, **kwargs)
                        result = Success(value) if not isinstance(value, (Success, Failure)) else value
                    else:
                        # Handle error and potentially continue
                        result, applied_fallback = self._apply_error_handling(result)
                        if not applied_fallback:
                            break
            except Exception as e:
                result = Failure(e)
                # Apply error handling for this step
                result, applied_fallback = self._apply_error_handling(result)
                if not applied_fallback:
                    break
        
        # Return the unwrapped value, or raise exception if failed
        if isinstance(result, Success):
            return result.unwrap()
        else:
            raise result.failure()


    def __iter__(self) -> Generator[Tuple[int, Callable, Dict], None, None]:
        """Iterate through the pipeline steps, yielding (index, callback, metadata) tuples."""
        for idx, (callback, metadata) in enumerate(zip(self._callbacks, self._callback_metadata)):
            yield idx, callback, metadata


    def __or__(self, default_value):
        """
        Set a fallback value to use when an error occurs in the pipeline.
        Pipeline should short-circuit (stop processing) after applying the fallback.
        """
        return self.handle_error(fallback=default_value, continue_pipeline=False)


    def __matmul__(self, other: '_Closure') -> '_Closure':
        """
        Support function composition with the @ operator.
        f @ g is equivalent to g(f(x))
        """
        if not isinstance(other, _Closure):
            raise TypeError(f"Expected _Closure, got {type(other).__name__}")
            
        result = copy(other)
        for cb, meta in zip(self._callbacks, self._callback_metadata):
            result._callbacks.append(cb)
            result._callback_metadata.append(meta)
            
        return result

    # Mathematical operations
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


# Utility functions to create Result-aware functions
def expects(factory: Callable) -> Callable:
    """
    Decorating a *factory* with @expects guarantees that the callable it
    returns is also marked as expecting a Result.
    """
    @wraps(factory)
    def wrapper(*a, **k):
        fn = factory(*a, **k)
        fn._expects_result = True        # mark the *returned* callable
        return fn
    wrapper._expects_result = True       # factory can still be used itself
    return wrapper


def partial(fn, /, *fixed_a, **fixed_k):
    """functools.partial that keeps  __name__, __doc__
       and propagates _expects_result when present."""
    new = functools.partial(fn, *fixed_a, **fixed_k)
    functools.update_wrapper(new, fn)
    if getattr(fn, '_expects_result', False):
        new._expects_result = True
    return new


# Main public API
def closure(fn: Optional[Callable] = None, debug: bool = False) -> _Closure:
    """
    Create a closure pipeline.
    
    Args:
      fn: 
        The first transformation function in the pipeline.
      debug:
        Optional flag to enable debug prints.

    Returns:
      A _Closure instance wrapping the initial function.
    """
    return _Closure(fn, debug=debug)


# Standalone transformation functions for Result monad
@expects
def add(n):
    """Returns a function that adds n to its input value."""
    def inner(result: Result, *args, **kwargs):
        return result.map(lambda x: x + n)
    inner.__name__ = f"add({n})"
    inner.__doc__ = f"Add {n} to the input value"
    return inner

@expects
def subtract(n):
    """Returns a function that subtracts n from its input value."""
    def inner(result: Result, *args, **kwargs):
        return result.map(lambda x: x - n)
    inner.__name__ = f"subtract({n})"
    inner.__doc__ = f"Subtract {n} from the input value"
    return inner

@expects
def multiply(n):
    """Returns a function that multiplies its input value by n."""
    def inner(result: Result, *args, **kwargs):
        return result.map(lambda x: x * n)
    inner.__name__ = f"multiply({n})"
    inner.__doc__ = f"Multiply the input value by {n}"
    return inner

@expects
def divide(n):
    """Returns a function that divides its input value by n."""
    if n == 0:
        raise ValueError("Cannot divide by zero")
    def inner(result: Result, *args, **kwargs):
        return result.map(lambda x: x / n)
    inner.__name__ = f"divide({n})"
    inner.__doc__ = f"Divide the input value by {n}"
    return inner

@expects
def exponentiate(n):
    """Returns a function that raises its input value to the power of n."""
    def inner(result: Result, *args, **kwargs):
        return result.map(lambda x: x ** n)
    inner.__name__ = f"exponentiate({n})"
    inner.__doc__ = f"Raise the input value to the power of {n}"
    return inner

@expects
def square(result: Result, *args, **kwargs):
    """Returns the square of the input value."""
    return result.map(lambda x: x ** 2)

@expects
def cube(result: Result, *args, **kwargs):
    """Returns the cube of the input value."""
    return result.map(lambda x: x ** 3)

@expects
def squareroot(result: Result, *args, **kwargs):
    """Returns the square root of the input value."""
    return result.bind(lambda x: 
        Success(x ** 0.5) if x >= 0 else 
        Failure(ValueError(f"Cannot compute square root of negative number: {x}")))

@expects
def cuberoot(result: Result, *args, **kwargs):
    """Returns the cube root of the input value."""
    return result.map(lambda x: x ** (1/3))

@expects
def root(n):
    """Returns a function that returns the nth root of its input value."""
    if n == 0:
        raise ValueError("Cannot compute 0th root")
    def inner(result: Result, *args, **kwargs):
        return result.bind(lambda x: 
            Success(x ** (1/n)) if not (n % 2 == 0 and x < 0) else
            Failure(ValueError(f"Cannot compute even root ({n}) of negative number: {x}")))
    inner.__name__ = f"root({n})"
    inner.__doc__ = f"Calculate the {n}th root of the input value"
    return inner

@expects
def linfunc(result: Result, *args, **kwargs):
    """Uses the provided linear parameters to process x."""
    try:
        import pandas as pd
        import numpy as np
        
        return result.bind(lambda params: 
            Failure(ValueError("params must contain at least (x, m, b)")) if not params or len(params) < 3 else
            Success((lambda x, m, b: pd.DataFrame({"x": x, "y": np.array([(m * n + b) for n in x])}))(*params[0:3]))
        )
    except ImportError:
        return Failure(ImportError("Required libraries missing: pandas, numpy"))

@expects
def linvis(result: Result, *args, **kwargs):
    """Creates a linear visualization from a DataFrame with x and y columns."""
    try:
        import seaborn as sns
        import seaborn.objects as so
        
        return result.bind(lambda df:
            Failure(ValueError("DataFrame must contain 'x' and 'y' columns")) if 'x' not in df.columns or 'y' not in df.columns else
            Success(
                so.Plot(data=df, x="x", y="y")
                .add(so.Line())
                .label(title="y = mx + b")
                .theme({
                    "figure.dpi": 300,
                    "font.family": "sans-serif"
                })
            )
        )
    except ImportError:
        return Failure(ImportError("Required library missing: seaborn"))

@expects
def to_dataframe(result: Result, *args, **kwargs):
    """Converts the pipeline result and original input to a DataFrame."""
    try:
        import pandas as pd
        import numpy as np
        
        if not args:
            return Failure(ValueError("No input values found in args"))
        
        input_val = args[0]
        
        def process_result(r):
            # Handle different input types
            if isinstance(input_val, (list, tuple, np.ndarray)) and not isinstance(r, (list, tuple, np.ndarray)):
                return Failure(ValueError(
                    "Cannot create DataFrame: array-like input resulted in scalar output. "
                    "The transformation might not preserve the array structure."
                ))
            
            # Create the DataFrame based on input and result types
            if isinstance(input_val, (list, tuple, np.ndarray)) and isinstance(r, (list, tuple, np.ndarray)):
                if len(input_val) != len(r):
                    return Failure(ValueError(
                        f"Input and output arrays have different lengths: {len(input_val)} vs {len(r)}"
                    ))
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
            
            return Success((input_val, df))
        
        return result.bind(process_result)
    except ImportError:
        return Failure(ImportError("Required libraries missing: pandas, numpy"))
    except Exception as e:
        return Failure(e)

@expects
def to_plot(result: Result, *args, **kwargs):
    """Plot the data resulted by a transformation pipeline."""
    try:
        import seaborn as sns
        import seaborn.objects as so
        
        return result.bind(lambda r:
            Failure(ValueError("Expected a tuple with at least (result, dataframe)")) if not isinstance(r, tuple) or len(r) < 2 else
            Success((lambda result, df: 
                (
                    result,
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
                    .limit(
                        x=(min(df["input"]) - 1, max(df["input"]) + 1),
                        y=(min(df["output"]) - 1, max(df["output"]) + 1)
                    ),
                    df
                )
            )(*r))
        )
    except ImportError:
        return Failure(ImportError("Required libraries missing: seaborn"))
    except Exception as e:
        return Failure(e)

# Standalone functions to be used with the + operator
def dataframe(r, *args, **kwargs):
    """Standalone function to convert pipeline results to a DataFrame."""
    # Handle Result type input
    if isinstance(r, Result):
        return to_dataframe(r, *args, **kwargs)
    else:
        return to_dataframe(Success(r), *args, **kwargs)

def plot(r, *args, **kwargs):
    """Standalone function to convert results to a seaborn.Plot."""
    # Handle Result type input
    if isinstance(r, Result):
        return to_plot(r, *args, **kwargs)
    else:
        return to_plot(Success(r), *args, **kwargs)

# Add method to create a linfunc closure
def _closure_linfunc(self):
    """Add a linear function operation to the pipeline."""
    return self.pipe(linfunc)

# Add method to create a linvis closure
def _closure_linvis(self):
    """Add a visualization operation to the pipeline."""
    return self.pipe(linvis)

# Add dataframe and plot methods to _Closure
def _closure_to_dataframe(self):
    """Add a DataFrame creation operation to the pipeline."""
    return self.pipe(to_dataframe)

def _closure_to_plot(self):
    """Add a Seaborn Plot creation operation to the pipeline."""
    return self.pipe(to_plot)

# Add the methods to the _Closure class
_Closure.linfunc = _closure_linfunc
_Closure.linvis = _closure_linvis
_Closure.to_dataframe = _closure_to_dataframe
_Closure.to_plot = _closure_to_plot

# Pre-composed pipeline
linplot = closure(linfunc) + linvis


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
