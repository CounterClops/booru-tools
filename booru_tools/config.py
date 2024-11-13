import tomllib
import validators
from loguru import logger

from pathlib import Path
from sys import platform
import os

# https://yozachar.github.io/pyvalidators/stable/api/url/

class ConfigDefaults:
    GLOBALS_DEFAULTS = {
        'url': None,
        'username': None,
        'api_token': None,
        'public': False,
        'hide_progress': False,
    }

    CREDENTIALS_DEFAULTS = {
        'pixiv': {'token': None},
    }

    LOGGING_DEFAULTS = {
        'log_enabled': False,
        'log_file': 'szurubooru_toolkit.log',
        'log_level': 'INFO',
        'log_colorized': True,
    }

class Config:
    def __init__(self) -> None:
        """
        Initializes a new instance of the Config class.

        This method sets the default configuration values for various components of the application. It also defines the
        default locations for the configuration file, which are different for Windows and Linux.

        The configuration values are stored as attributes of the Config instance. Each attribute is a dictionary containing
        the default configuration values for a specific component of the application.

        Args:
            None

        Returns:
            None
        """

        self.globals = ConfigDefaults.GLOBALS_DEFAULTS
        self.logging = ConfigDefaults.LOGGING_DEFAULTS
        self.credentials = ConfigDefaults.CREDENTIALS_DEFAULTS

        self.config_file = "config.toml"
    
    def load_toml(self, config_file:Path) -> None:
        with open(config_file, 'rb') as file:
            try:
                config = tomllib.load(file)
                for section, values in config.items():
                    if hasattr(self, section):
                        getattr(self, section).update(values)
            except Exception as e:
                logger.critical(e)
                exit(1)

    def load_config_files(self) -> None:
        default_locations = [
            Path().absolute() / self.config_file,
            Path.home().absolute() / "booru-tools" / self.config_file
        ]

        if platform == "win32":
            default_locations.extend([
                Path(os.environ['APPDATA']) / "booru-tools" / self.config_file
            ])
        else:
            default_locations.extend([
                Path('/etc/booru-tools') / {self.config_file}
            ])
        
        for location in default_locations:
            if location.is_file():
                logger.debug(f"Found config at '{location}'")
                config_file = location
                break
            config_file = None
        
        if config_file:
            self.load_toml(config_file=config_file)
            self.validate_config()

    def validate_config(self) -> None:
        pass

    def override_config(self, overrides: dict) -> None:
        """Override options with command line arguments.

        Args:
            overrides (dict): A dictionary containing the options to override.
        """

        for section, items in overrides.items():
            section_dict = getattr(self, section)
            for item in items:
                section_dict[item] = items[item]
            setattr(self, section, section_dict)
        
        self.validate_config()