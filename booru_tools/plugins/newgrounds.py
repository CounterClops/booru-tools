import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "newgrounds.com"
    ]
    _CATEGORY = [
        "newgrounds"
    ]
    _NAME = "newgrounds"

    URL_BASE = "https://www.newgrounds.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/search/summary?terms="
    
    POST_CATEGORY_MAP = {}

class NewgroundsValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[w.]*newgrounds\.com\/portal\/view\/\d+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/(?!www\.)\w+\.newgrounds\.com)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[w.]*newgrounds\.com\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT