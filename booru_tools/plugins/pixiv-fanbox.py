import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "fanbox.cc"
    ]
    _CATEGORY = [
        "fanbox"
    ]
    _NAME = "fanbox"

    URL_BASE = "https://www.fanbox.cc/"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

class PixivValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = None
    USER_URL_PATTERN = None
    GLOBAL_URL_PATTERN = None