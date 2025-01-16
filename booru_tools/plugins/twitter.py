import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "twitter.com",
        "x.com"
    ]
    _CATEGORY = [
        "twitter"
    ]
    _NAME = "twitter"

    URL_BASE = "https://x.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

class TwitterValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/.+\/status\/\d+)|(https:\/\/[a-zA-Z0-9.-]+\/media\/.+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/[^/]+\/?$)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT