from pathlib import Path
from loguru import logger
from typing import Any
from dataclasses import asdict, fields

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

    def merge_data(self, data:dict|_default_configs.DefaultConfigBaseGroup) -> dict:
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
                if not value:
                    continue
                logger.debug(f"Setting key '{key}' to {value}")
                self[key] = value
        return self

class ConfigManager(ConfigGroup):
    def __init__(self, default_dataclass):
        logger.debug(f"loading default values into config manager")
        self.default_dataclass = default_dataclass
        self.merge_data(asdict(default_dataclass))

        logger.debug(f"loading config file if present")
        config_file = self._find_default_config_file()
        self._load_config_file(config_file)

        self._validate_config(data=self, default_dataclass=self.default_dataclass)

    def _load_config_file(self, config_file:Path):
        if config_file.suffix == ".yaml":
            self._load_yaml(config_file)

    def _find_default_config_file(self) -> Path:
        config_file = Path("config.yaml")
        if config_file.exists():
            logger.debug(f"found config file: {config_file}")
            return config_file

    def _load_yaml(self, config_file:Path):
        logger.debug(f"loading config file: {config_file}")
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        self.merge_data(data)
    
    def _validate_config(self, data:dict, default_dataclass:_default_configs.DefaultConfigBaseGroup):
        data_keys = data.keys()
        for field in fields(default_dataclass):
            try:
                value = dict.__getitem__(data, field.name)
            except KeyError as e:
                continue

            if isinstance(value, dict):
                logger.debug(f"validating nested config: {field.name}")
                self._validate_config(data=value, default_dataclass=field.type)
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
                exit()
            
shared_config_manager = ConfigManager(
    default_dataclass=_default_configs.DefaultConfig()
)