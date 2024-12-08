from loguru import logger

class PluginBase():
    _DOMAINS:list[str] = []
    _CATEGORY:list[str] = []
    _NAME:str = ""

    def __init__(self, config:dict={}):
        logger.debug(f"Loaded {self.__class__.__name__}")
        self.import_config(config=config)

    def import_config(self, config:dict={}):
        for key, value in config.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        raise NotImplementedError(f"'{self.__class__.__name__}' object has no attribute '{name}'")