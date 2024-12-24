import re

from booru_tools.shared import constants
from booru_tools.plugins import _plugin_template

class SharedAttributes:
    _DOMAINS = [
        "derpibooru.org",
        "derpicdn.net"
    ]
    _CATEGORY = [
        "derpibooru"
    ]
    _NAME = "derpibooru"

    URL_BASE = "https://derpibooru.org"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/images"
    
    POST_CATEGORY_MAP = {
        "0": constants.Category.GENERAL,
        "1": constants.Category.ARTIST,
        "3": constants.Category.COPYRIGHT,
        "4": constants.Category.CHARACTER,
        "5": constants.Category.META
    }

class DerpibooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/images\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/img\/view\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT