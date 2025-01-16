import tomllib
from loguru import logger
from pathlib import Path

# https://yozachar.github.io/pyvalidators/stable/api/url/

class ConfigDefaults:
    pass

class ConfigManager:
    def __init__(self):
        self.config = {}

    def load(self, config_file:Path):
        with open(config_file, mode="rb") as file:
            self.config = tomllib.load(file)