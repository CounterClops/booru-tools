import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "bsky.app"
    ]
    _CATEGORY = [
        "bluesky"
    ]
    _NAME = "bluesky"

    URL_BASE = "https://bsky.app"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/search"
    
    POST_CATEGORY_MAP = {}

class BlueskyValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z.-]+\/profile\/.+\/post\/.+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z.-]+\/profile\/.+\/?$)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT