import importlib.util
import inspect
from pathlib import Path

from dataclasses import dataclass
from loguru import logger

@dataclass
class Plugin:
    name: str
    module_name: str
    obj: type

    def __str__(self) -> str:
        return f"Plugin: {self.obj.__class__.__name__} ({self.module_name})"
    
    def __call__(self, *args, **kwargs):
        logger.debug(f"Calling '{self}'")
        return self.obj(*args, **kwargs)

class PluginLoader:
    def __init__(self, plugin_class: type):
        self.plugins = []
        self.plugin_class = plugin_class

    # Function to load all plugins (Python files) in a directory
    def load_plugins_from_directory(self, directory: Path) -> list:
        """Goes through all python modules in a directory and returns a list of Classes from those modules that match the self.plugin_class

        Args:
            directory (Path): The directory to search for python modules, this is not recursive

        Returns:
            list: The list of python classes that have been loaded into this PluginLoader instance
        """
        print(directory.absolute())
        for plugin_path in directory.glob('*.py'):
            if plugin_path.name == '__init__.py':  # Skip __init__.py
                continue
            
            module_name = plugin_path.stem
            logger.debug(f"Checking module '{module_name}' for desired plugins")
            
            # Dynamically load the module
            spec = importlib.util.spec_from_file_location(module_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find classes in the module that are subclasses of `self.plugin_class`
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, self.plugin_class) and obj != self.plugin_class:
                    logger.debug(f"Loaded '{obj.__class__.__name__}' as '{name}'")
                    plugin = Plugin(
                        name=name,
                        module_name=module_name,
                        obj=obj
                    )
                    
                    self.plugins.append(plugin)
        
        logger.debug(f"Loaded {len(self.plugins)} plugins")        
        return self.plugins

class NoPluginFound(Exception):
    pass