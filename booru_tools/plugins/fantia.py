from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants
from loguru import logger
import re

class SharedAttributes:
    _DOMAINS = [
        "fantia.jp"
    ]
    _CATEGORY = [
        "fantia"
    ]
    _NAME = "fantia"

    URL_BASE = "https://fantia.jp"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}"
    
    POST_CATEGORY_MAP = {}

class FantiaValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/posts\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT