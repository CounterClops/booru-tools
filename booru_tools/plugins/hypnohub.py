import re

from booru_tools.plugins import _plugin_template, gelbooru
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "hypnohub.net"
    ]
    _CATEGORY = []
    _NAME = "hypnohub"

    URL_BASE = "https://hypnohub.net"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=post&s=list&tags=all"
    
    POST_CATEGORY_MAP = {}

class HypnoHubMeta(SharedAttributes, gelbooru.GelbooruMeta):
    pass

class HypnoHubValidator(SharedAttributes, gelbooru.GelbooruValidator):
    pass