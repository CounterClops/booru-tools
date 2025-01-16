import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "chan.sankakucomplex.com",
        "idol.sankakucomplex.com",
        "sankakucomplex.com"
    ]
    _CATEGORY = [
        "sankaku"
    ]
    _NAME = "sankaku"

    URL_BASE = "https://chan.sankakucomplex.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/?tags="
    
    POST_CATEGORY_MAP = {}

class SankakuValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/.+\/posts\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/data\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT