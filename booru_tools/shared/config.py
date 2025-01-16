import yaml
import os
from pathlib import Path

class _Singleton(type):
    _instance = None
    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance

class Config(metaclass=_Singleton):
    def __init__(self):
        config_file = self._find_default_config_file()
        self._load_config_file(config_file)

    def _load_config_file(self, config_file:Path):
        if config_file.suffix == ".yaml":
            self._load_yaml(config_file)

    def _find_default_config_file(self) -> Path:
        config_file = Path("config.yaml")
        if config_file.exists():
            return config_file

    def _load_yaml(self, config_file:Path):
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        for key, value in data.items():
            object.__setattr__(self, key, value)