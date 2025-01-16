import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "yande.re"
    ]
    _CATEGORY = [
        "yandere"
    ]
    _NAME = "yandere"

    URL_BASE = "https://yande.re"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/post"
    
    POST_CATEGORY_MAP = {}

class YandereValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/post\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/image\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/sample\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT