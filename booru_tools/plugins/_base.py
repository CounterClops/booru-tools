from loguru import logger

from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS:list[str] = []
    _CATEGORY:list[str] = []
    _NAME:str = ""

    POST_CATEGORY_MAP:dict = {}
    POST_SAFETY_MAPPING:dict = {
        "safe": constants.Safety.SAFE,
        "sketchy": constants.Safety.SKETCHY,
        "unsafe": constants.Safety.UNSAFE
    }

    URL_BASE = ""
    
    @property
    def DEFAULT_POST_SEARCH_URL(self):
        if self.URL_BASE:
            return f"{self.URL_BASE}/posts"
        return ""

class PluginBase(SharedAttributes):
    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")

    def __getattr__(self, name):
        raise NotImplementedError(f"'{self.__class__.__name__}' object has no attribute '{name}'")