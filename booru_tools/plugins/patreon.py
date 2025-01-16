import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "patreon.com"
    ]
    _CATEGORY = [
        "patreon"
    ]
    _NAME = "patreon"

    URL_BASE = "https://www.patreon.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

class PatreonValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/posts\/.+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/c\/.+\/?)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT