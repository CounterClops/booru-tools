import importlib.util
import inspect
from pathlib import Path
import functools

from dataclasses import dataclass
from loguru import logger
from booru_tools.plugins import _base
from booru_tools.shared import errors


@dataclass(kw_only=True)
class InternalPlugin:
    name: str
    module_name: str
    obj: _base.PluginBase

    def __str__(self) -> str:
        return f"Plugin: {self.obj.__class__.__name__} ({self.module_name})"
    
    def __call__(self, *args, **kwargs):
        logger.debug(f"Calling '{self}'")
        return self.obj(*args, **kwargs)

class PluginLoader:
    def __init__(self, plugin_class: type):
        self.plugins:list[InternalPlugin] = []
        self.plugin_class:_base.PluginBase = plugin_class
        self.plugin_configs:dict[str, dict] = {
            "szurubooru" : {
                "url_base": "https://szurubooru.equus.soy",
                "username": "e621-sync",
                "password": "7dc645f5-b525-43b0-a27b-3362d5e8bb2f"
            }
        }

    # Function to load all plugins (Python files) in a directory
    def load_plugins_from_directory(self, directory: Path) -> list[InternalPlugin]:
        """Goes through all python modules in a directory and returns a list of Classes from those modules that match the self.plugin_class

        Args:
            directory (Path): The directory to search for python modules, this is not recursive

        Returns:
            list[InternalPlugin]: The list of python classes that have been loaded into this PluginLoader instance
        """

        for plugin_path in directory.glob('*.py'):
            if plugin_path.name.startswith("_"): # Skipping plugins that start with _
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
                    plugin = InternalPlugin(
                        name=name,
                        module_name=module_name,
                        obj=obj
                    )
                    
                    self.plugins.append(plugin)
        
        logger.debug(f"Loaded {len(self.plugins)} plugins")        
        return self.plugins

    def get_plugin_config(self, plugin_name:str) -> dict:
        try:
            logger.debug(f"Checking for config to '{plugin_name}' plugin")
            config = self.plugin_configs[plugin_name]
            logger.debug(f"Found plugin config for '{plugin_name}'")
        except (AttributeError, KeyError):
            logger.debug(f"No plugin config found for '{plugin_name}'")
            config = {}
        return config

    def find_plugin(self, domain:str="", category:str="") -> InternalPlugin:
        """Find plugin that matches the desired service, it will return a plugin if any single condition matches

        Args:
            domain (list, optional): The domain of the service to match with the plugin. Defaults to [].
            category (list, optional): The category of the service to match with the plugin. Defaults to [].

        Raises:
            errors.NoPluginFound: When a plugin that matches the provided criteria isn't found in the provided list of plugins

        Returns:
            InternalPlugin: The first plugin to match the desired conditions
        """
        logger.debug(f"Searching {len(self.plugins)} {self.plugin_class.__class__.__name__} plugins for domain={domain}, category={category}")

        for plugin in self.plugins:
            try:
                plugin_domains = plugin.obj._DOMAINS
                logger.debug(f"Domain search: '{domain}' in '{plugin_domains}'")
                plugin_domain_matches = any(plugin_domain in domain for plugin_domain in plugin_domains)
                if plugin_domain_matches:
                    logger.debug(f"Found '{plugin}' with domain match")
                    return plugin
            except (TypeError, AttributeError):
                pass
            
            try:
                plugin_category = plugin.obj._CATEGORY
                logger.debug(f"Category search: '{category}' in '{plugin_category}'")
                plugin_category_matches = any(category in plugin_category for plugin_category in plugin_category)
                if plugin_category_matches:
                    logger.debug(f"Found '{plugin}' with category match")
                    return plugin
            except (TypeError, AttributeError):
                pass
            
        raise errors.NoPluginFound
    
    @functools.cache
    def init_plugin(self, domain:str="", category:str="") -> _base.PluginBase:
        logger.debug(f"Starting search for {self.plugin_class.__class__.__name__} plugin with domain={domain}, category={category}")

        plugin:InternalPlugin = self.find_plugin(
            domain=domain,
            category=category
        )

        config:dict = self.get_plugin_config(
            plugin_name=plugin.obj._NAME
        )

        initialised_plugin:_base.PluginBase = plugin(config=config)

        return initialised_plugin