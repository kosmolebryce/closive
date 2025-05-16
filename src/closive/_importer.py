"""Custom import functionality for closive.

This module provides welcome messages and external pipeline loading
when the closive package is imported.
"""

import os
import yaml
from pathlib import Path
import importlib
from typing import Dict, Any


def display_welcome_message():
    """Display a welcome message when closive is imported."""
    print("\033[1;36m" + "Closive: Data Transformatics - v0.0.0" + "\033[0m")
    print("💡 Tip: Use closure(fn) & next_fn to create transformation pipelines.")
    print("📄 Documentation: https://github.com/kosmolebryce/closive")


def load_external_pipelines() -> Dict[str, Any]:
    """Load external pipelines from the user's configuration file."""
    config_path = Path.home() / ".local" / "share" / "closive" / "pipelines.yml"
    if not config_path.exists():
        return {}
    
    try:
        with open(config_path, 'r') as f:
            pipeline_configs = yaml.safe_load(f)
        
        if not pipeline_configs:
            return {}
        
        return process_pipeline_configs(pipeline_configs)
    except Exception as e:
        print(f"\033[33mWarning: Failed to load external pipelines: {e}\033[0m")
        return {}


def process_pipeline_configs(configs: Dict) -> Dict[str, Any]:
    """Process the pipeline configurations and return the constructed pipelines."""
    from closive.closures import closure
    
    result = {}
    
    for name, config in configs.items():
        try:
            if not isinstance(config, dict) or 'steps' not in config:
                print(f"\033[33mWarning: Invalid pipeline configuration for '{name}'\033[0m")
                continue
            
            # Load the functions for each step
            steps = []
            for step in config['steps']:
                if isinstance(step, dict):
                    fn_module = step.get('module')
                    fn_name = step.get('function')
                    args = step.get('args', [])
                    kwargs = step.get('kwargs', {})
                    
                    if not fn_module or not fn_name:
                        print(f"\033[33mWarning: Invalid step in pipeline '{name}'\033[0m")
                        continue
                    
                    # Import the module and get the function
                    try:
                        module = importlib.import_module(fn_module)
                        fn = getattr(module, fn_name)
                        
                        # If the function needs arguments, call it with the arguments
                        if args or kwargs:
                            fn = fn(*args, **kwargs)
                        
                        steps.append(fn)
                    except (ImportError, AttributeError) as e:
                        print(f"\033[33mWarning: Failed to import {fn_module}.{fn_name}: {e}\033[0m")
                        continue
                else:
                    print(f"\033[33mWarning: Invalid step format in pipeline '{name}'\033[0m")
                    continue
            
            if not steps:
                print(f"\033[33mWarning: No valid steps found for pipeline '{name}'\033[0m")
                continue
            
            # Create the pipeline
            pipeline = closure(steps[0])
            for step in steps[1:]:
                pipeline = pipeline & step
            
            result[name] = pipeline
        except Exception as e:
            print(f"\033[33mWarning: Failed to create pipeline '{name}': {e}\033[0m")
    
    return result


def reload_pipelines():
    """Reload all external pipelines."""
    pipelines = load_external_pipelines()
    # Add pipelines to the closive module
    import closive
    for name, pipeline in pipelines.items():
        setattr(closive, name, pipeline)
        # Add to __all__ if it exists
        if hasattr(closive, '__all__'):
            if name not in closive.__all__:
                closive.__all__ = list(closive.__all__) + [name]
    return list(pipelines.keys())


def save_pipeline(name: str, pipeline, description: str = None):
    """Save a pipeline to the user's configuration file."""
    config_dir = Path.home() / ".local" / "share" / "closive"
    config_path = config_dir / "pipelines.yml"
    
    # Create the directory if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Load existing configuration
    if config_path.exists():
        with open(config_path, 'r') as f:
            configs = yaml.safe_load(f) or {}
    else:
        configs = {}
    
    # Convert the pipeline to a configuration
    pipeline_config = {
        'description': description or f"Pipeline {name}",
        'steps': []
    }
    
    # Extract steps from the pipeline
    callbacks = pipeline.callbacks
    for callback in callbacks:
        module_name = callback.__module__
        function_name = callback.__name__
        
        # Check if this is a function produced by another function (like add(5))
        if '(' in function_name and ')' in function_name:
            # Try to parse the function and its arguments
            try:
                base_name = function_name.split('(')[0]
                args_str = function_name.split('(')[1].split(')')[0]
                args = [eval(arg.strip()) for arg in args_str.split(',') if arg.strip()]
                
                step = {
                    'module': module_name,
                    'function': base_name,
                    'args': args
                }
            except:
                # Fallback if we can't parse the function
                step = {
                    'module': module_name,
                    'function': function_name
                }
        else:
            step = {
                'module': module_name,
                'function': function_name
            }
        
        pipeline_config['steps'].append(step)
    
    # Save the configuration
    configs[name] = pipeline_config
    with open(config_path, 'w') as f:
        yaml.dump(configs, f, default_flow_style=False)
    
    return True


def create_default_config():
    """Create the default pipelines.yml configuration file if it doesn't exist."""
    config_dir = Path.home() / ".local" / "share" / "closive"
    config_path = config_dir / "pipelines.yml"
    
    if not config_path.exists():
        # Create the directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a default configuration file
        default_config = {
            "example_pipeline": {
                "description": "An example pipeline that squares a number and adds 5",
                "steps": [
                    {
                        "module": "closive.closures",
                        "function": "square"
                    },
                    {
                        "module": "closive.closures",
                        "function": "add",
                        "args": [5]
                    }
                ]
            }
        }
        
        with open(config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        
        print(f"Created default configuration file at {config_path}")
