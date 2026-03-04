import re

from booru_tools.plugins import _plugin_template, gelbooru
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "tbib.org"
    ]
    _CATEGORY = [
        "tbib"
    ]
    _NAME = "tbib"

    URL_BASE = "https://tbib.org"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=dapi&s=post&q=index"
    
    POST_CATEGORY_MAP = {}

class TheBigImageBoardMeta(SharedAttributes, gelbooru.GelbooruMeta):
    pass