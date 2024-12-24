import re

from booru_tools.shared import constants
from booru_tools.plugins import _plugin_template

class SharedAttributes:
    _DOMAINS = [
        "furaffinity.net"
    ]
    _CATEGORY = [
        "furaffinity"
    ]
    _NAME = "furaffinity"

    URL_BASE = "https://www.furaffinity.net"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

class FurAffinityValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/view\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/art\/.+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/user\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT