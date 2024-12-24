from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants
from loguru import logger
import re

class SharedAttributes:
    _DOMAINS = [
        "safebooru.org"
    ]
    _CATEGORY = [
        "safebooru"
    ]
    _NAME = "safebooru"

    URL_BASE = "https://safebooru.org"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=post&s=list&tags=all"
    
    POST_CATEGORY_MAP = {}

class SafebooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/index.php.+)|(https:\/\/[a-zA-Z0-9.-]+\/+samples\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/+images\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT