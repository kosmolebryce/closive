"""JIT Compilation

Implementation of JIT compilation for Closive Library.
"""

import inspect
import ast
import textwrap
import hashlib
from functools import lru_cache


class PipelineOptimizer:
    """Optimizes pipelines by compiling them into single functions."""
    
    def __init__(self):
        self._cache = {}
    
    @lru_cache(maxsize=128)
    def optimize(self, pipeline):
        """Convert a pipeline into an optimized single function."""
        # Generate a unique key for this pipeline
        pipeline_key = self._generate_pipeline_key(pipeline)
        
        # Check if we've already optimized this pipeline
        if pipeline_key in self._cache:
            return self._cache[pipeline_key]
        
        # Extract operations from the pipeline
        operations = self._analyze_pipeline(pipeline)
        
        # Generate the optimized function
        optimized_fn = self._generate_optimized_function(operations)
        
        # Cache the result
        self._cache[pipeline_key] = optimized_fn
        
        return optimized_fn
    
    def _generate_pipeline_key(self, pipeline):
        """Generate a unique key for a pipeline based on its operations."""
        key_parts = []
        
        for idx, callback, metadata in pipeline:
            # Get function source if possible
            try:
                source = inspect.getsource(callback)
            except (TypeError, OSError):
                # Fallback to function name and id if source not available
                source = f"{callback.__name__}_{id(callback)}"
            
            key_parts.append(f"{idx}:{source}")
        
        # Create a hash of all parts
        key = hashlib.md5(''.join(key_parts).encode('utf-8')).hexdigest()
        return key
    
    def _analyze_pipeline(self, pipeline):
        """Extract operation sequence from a pipeline."""
        operations = []
        
        for idx, callback, metadata in pipeline:
            # Try to determine if the function is pure
            is_pure = self._is_pure_function(callback)
            
            # Extract any error handling associated with this step
            error_handlers = self._extract_error_handlers(pipeline)
            
            operations.append({
                'function': callback,
                'name': metadata['name'],
                'is_pure': is_pure,
                'error_handlers': error_handlers
            })
        
        return operations
    
    def _is_pure_function(self, func):
        """
        Attempt to determine if a function is pure (no side effects).
        This is a best-effort analysis and may not be accurate in all cases.
        """
        try:
            # Try to get the source code
            source = inspect.getsource(func)
            
            # Parse the source code
            tree = ast.parse(textwrap.dedent(source))
            
            # Look for indications of impurity
            for node in ast.walk(tree):
                # Check for calls to impure built-ins
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in ['print', 'input', 'open']:
                        return False
                
                # Check for assignments to global variables
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and not self._is_local_var(tree, target.id):
                            return False
            
            # No obvious impurities found
            return True
        except (TypeError, SyntaxError, OSError):
            # If we can't analyze the function, assume it's not pure
            return False
    
    def _is_local_var(self, tree, var_name):
        """Check if a variable name is defined locally in the function."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if arg.arg == var_name:
                        return True
        return False
    
    def _extract_error_handlers(self, pipeline):
        """Extract error handling configuration from a pipeline."""
        handlers = {}
        
        # Check for various error handling attributes
        if hasattr(pipeline, "_default_on_error"):
            handlers['fallback'] = pipeline._default_on_error
        
        if hasattr(pipeline, "_error_handler"):
            handlers['handler'] = pipeline._error_handler
        
        if hasattr(pipeline, "_continue_after_fallback"):
            handlers['continue_pipeline'] = pipeline._continue_after_fallback
        
        if hasattr(pipeline, "_preserve_error_context"):
            handlers['preserve_context'] = pipeline._preserve_error_context
            
        if hasattr(pipeline, "_handled_error_types"):
            handlers['for_errors'] = pipeline._handled_error_types
            
        if hasattr(pipeline, "_propagate_other_errors"):
            handlers['propagate_others'] = pipeline._propagate_other_errors
        
        return handlers
    
    def _generate_optimized_function(self, operations):
        """Generate an optimized function from the operation list."""
        # First create the error handling function we'll need
        def handle_pipeline_error(error, args=None, kwargs=None, handlers=None):
            if not handlers:
                raise error
            
            # Check if we should handle this error type
            if 'for_errors' in handlers and handlers['for_errors'] is not None:
                if not isinstance(error, handlers['for_errors']):
                    if handlers.get('propagate_others', True):
                        raise error
            
            # Apply dynamic handler if available
            if 'handler' in handlers:
                try:
                    if handlers.get('preserve_context', False):
                        result = (handlers['handler'](error), error)
                    else:
                        result = handlers['handler'](error)
                    
                    # Check if we should continue the pipeline
                    if not handlers.get('continue_pipeline', False):
                        return result
                    
                    # Otherwise continue with the result
                    return result
                except Exception:
                    # If handler fails, fall back to static value
                    if 'fallback' in handlers:
                        if handlers.get('preserve_context', False):
                            return (handlers['fallback'], error)
                        else:
                            return handlers['fallback']
                    else:
                        raise
            
            # Apply static fallback
            elif 'fallback' in handlers:
                if handlers.get('preserve_context', False):
                    return (handlers['fallback'], error)
                else:
                    return handlers['fallback']
            
            # No handler or fallback, re-raise
            else:
                raise error
        
        # Now build a function that inlines all the operations
        def optimized_fn(x, *args, **kwargs):
            # Collect all error handlers
            all_handlers = {}
            for op in operations:
                if op['error_handlers']:
                    all_handlers.update(op['error_handlers'])
            
            try:
                result = x
                
                # Apply each operation in sequence
                for op in operations:
                    # For pure functions, inline the operation
                    if op['is_pure']:
                        result = op['function'](result, *args, **kwargs)
                    else:
                        # For non-pure functions, call them directly
                        result = op['function'](result, *args, **kwargs)
                
                return result
            except Exception as e:
                # Apply unified error handling
                return handle_pipeline_error(e, args, kwargs, all_handlers)
        
        return optimized_fn


# Function decorator for optimizing pipelines
def optimize(pipeline_or_closure):
    """
    Decorator that optimizes a pipeline by compiling it into a single function.
    
    Args:
        pipeline_or_closure: A pipeline or closure function to optimize
        
    Returns:
        An optimized version of the pipeline that executes faster
        
    Examples:
        # Optimize a pipeline
        @optimize(closure(lambda x: x + 1).square().multiply(2))
        def calculate(x):
            return x
            
        # This runs faster than the non-optimized version
        result = calculate(5)
    """
    # Get the pipeline object
    if callable(pipeline_or_closure) and hasattr(pipeline_or_closure, '_closure'):
        pipeline = pipeline_or_closure._closure
    else:
        pipeline = pipeline_or_closure
    
    # Create optimizer and optimize the pipeline
    optimizer = PipelineOptimizer()
    optimized_fn = optimizer.optimize(pipeline)
    
    # Return a decorator that replaces the function with the optimized pipeline
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            # Call the original function to get the input value
            input_value = func(*args, **kwargs)
            # Apply the optimized pipeline
            return optimized_fn(input_value, *args, **kwargs)
        
        # Store the original pipeline for introspection
        wrapped._original_pipeline = pipeline
        wrapped._optimized = True
        
        return wrapped
    
    return decorator