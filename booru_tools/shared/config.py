from pathlib import Path
from loguru import logger
from typing import Any
from dataclasses import asdict, fields, is_dataclass

import yaml
import os

from booru_tools.shared import _default_configs

class ConfigGroup(dict):
    def __init__(self, data=None):
        super().__init__()
        data = data or {}
        self._default_type = dict

        for key, value in data.items():
            if isinstance(value, dict):
                self[key] = ConfigGroup(value)
            else:
                self[key] = value

    def __getitem__(self, key):
        try:
            value = super().__getitem__(key)
        except KeyError as e:
            if self._default_type == dict:
                value = ConfigGroup()
            else:
                value = None
            self[key] = value
        return value

    def __setitem__(self, key, value):
        if not (isinstance(value, dict) or isinstance(value, ConfigGroup)):
            self._default_type = None

        if isinstance(value, dict):
            super().__setitem__(key, ConfigGroup(value))
        super().__setitem__(key, value)

    def merge_data(self, data:dict|_default_configs.DefaultConfigBaseGroup) -> "ConfigGroup":
        """Merge the provided data into the config group.

        Args:
            data (dict | _default_configs.DefaultConfigBaseGroup): The data to merge into the config group.

        Returns:
            ConfigGroup: The updated config group with the merged data
        """
        if isinstance(data, _default_configs.DefaultConfigBaseGroup):
            raw_data:dict[str, Any] = asdict(data)
            data = {}
            for key, value in raw_data.items():
                key = key.rstrip("_")
                data[key] = value

        for key, value in data.items():
            logger.debug(f"merging key: {key}")
            if isinstance(value, dict):
                if key in self:
                    current_value = self[key]
                    logger.debug(f"Merging nested data for '{key}'")
                    value = current_value.merge_data(value)
                logger.debug(f"Adding new '{key}' to config")
                self[key] = ConfigGroup(value)
            else:
                if value is None:
                    continue
                logger.debug(f"Setting key '{key}' to {value}")
                self[key] = value
        return self

class ConfigManager(ConfigGroup):
    def __init__(self, default_dataclass, load_envars=False):
        logger.debug(f"loading default values into config manager")
        self.default_dataclass = default_dataclass
        self.merge_data(asdict(default_dataclass))

        logger.debug(f"loading config file if present")
        config_file = self._find_default_config_file()
        self._load_config_file(config_file)
        
        if load_envars:
            self._load_envars()

        self._validate_config(data=self, default_dataclass=self.default_dataclass)

    def _load_config_file(self, config_file:Path) -> None:
        """Load the provided config file into the config manager.

        Args:
            config_file (Path): The path of the config file to load.
        """
        if config_file.suffix == ".yaml":
            self._load_yaml(config_file)
    
    def _load_envars(self) -> None:
        """Load environment variables into the config manager.
        Environment variables should be in the format of:
            <config_key>__<nested_key>__<nested_key>__... = value
        """
        config = {}

        envar_map = self._get_envar_keys(dataclass=self.default_dataclass)
        for envar_key, envar_type in envar_map.items():
            envar_value = os.getenv(envar_key)
            if envar_value is None:
                continue

            logger.debug(f"Found envar: {envar_key} with value: {envar_value}")

            envar_key_path = envar_key.lower().split("__")
            nested_config = config
            for envar_key in envar_key_path[:-1]:
                try:
                    nested_config = nested_config[envar_key]
                except KeyError as e:
                    nested_config[envar_key] = {}
                    nested_config = nested_config[envar_key]

            if envar_type == list:
                envar_value = [envar_item.strip() for envar_item in envar_value.split(",")]
            elif envar_type == bool:
                envar_value = envar_value.lower() in ["true", "1", "yes"]
            
            nested_config[envar_key_path[-1]] = envar_type(envar_value)
        
        self.merge_data(config)

    @staticmethod
    def _find_default_config_file() -> Path:
        """Check for the presence of a default config file in the default lookup directories.

        Returns:
            Path: The found config file path.
        """
        config_file = Path("config.yaml")
        if config_file.exists():
            logger.debug(f"found config file: {config_file}")
            return config_file

    def _load_yaml(self, config_file:Path):
        logger.debug(f"loading config file: {config_file}")
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.merge_data(data)
    
    @classmethod
    def _get_envar_keys(cls, dataclass:_default_configs.DefaultConfigBaseGroup) -> dict[str, type]:
        """Create a mapping of environment variable keys to their respective types, based on the provided default config dataclass.

        Args:
            dataclass (_default_configs.DefaultConfigBaseGroup): The dataclass to use as the template for default values and their types.

        Returns:
            dict[str, type]: The mapping of environment variable keys to their respective types.
        """
        envar_map = {}
        for field in fields(dataclass):
            field_name = field.name.upper()
            if is_dataclass(field.type):
                child_envar_keys = cls._get_envar_keys(dataclass=field.type())
                for envar_key, envar_type in child_envar_keys.items():
                    envar_map[f"{field_name}__{envar_key}"] = envar_type
                continue
            key_name = field.name.upper()
            envar_map[key_name] = field.type
        return envar_map

    @classmethod
    def _validate_config(cls, data:dict, default_dataclass:_default_configs.DefaultConfigBaseGroup) -> None:
        """Validates the provided config data against the provided default dataclass, to ensure that all values are of the correct type.

        Args:
            data (dict): The config data to validate.
            default_dataclass (_default_configs.DefaultConfigBaseGroup): The default dataclass to use as the template for default values and their types.
        """
        data_keys = data.keys()
        for field in fields(default_dataclass):
            try:
                value = dict.__getitem__(data, field.name)
            except KeyError as e:
                continue

            if isinstance(value, dict):
                logger.debug(f"validating nested config: {field.name}")
                cls._validate_config(data=value, default_dataclass=field.type)
                continue
            
            if field.name not in data_keys:
                continue

            logger.debug(f"validating field: {field.name} is {field.type.__name__}")
            try:
                data[field.name] = field.type(
                    value
                )
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid value for field: {field.name} {value} cannot convert to type {field.type.__name__}")
                logger.warning(f"Removing invalid field: {field.name} to avoid unexpected behavior")
                data.pop(field.name)

shared_config_manager = ConfigManager(
    default_dataclass=_default_configs.DefaultConfig(),
    load_envars=True
)