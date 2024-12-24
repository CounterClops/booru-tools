from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants
from loguru import logger
import re

class SharedAttributes:
    _DOMAINS = [
        "gelbooru.com"
    ]
    _CATEGORY = [
        "gelbooru"
    ]
    _NAME = "gelbooru"

    URL_BASE = "https://gelbooru.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=post&s=list&tags="
    
    POST_CATEGORY_MAP = {}

class GelbooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/.+page=post.+)|(https:\/\/[a-zA-Z0-9.-]+\/+samples\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT