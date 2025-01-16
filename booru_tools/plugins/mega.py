import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "mega.nz"
    ]
    _CATEGORY = [
        "mega"
    ]
    _NAME = "mega"

    URL_BASE = "https://mega.nz"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

class MegaValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/file\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT