import re

from booru_tools.plugins import _plugin_template, gelbooru
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "rule34.xxx"
    ]
    _CATEGORY = [
        "rule34"
    ]
    _NAME = "rule34"

    URL_BASE = "https://rule34.xxx"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=dapi&s=post&q=index"
    
    POST_CATEGORY_MAP = {}

    DOWNLOADER_CONFIG = {
        "extractor": "gelbooru_v02"
    }

class Rule34XxxMeta(SharedAttributes, gelbooru.GelbooruMeta):
    pass

class Rule34XxxValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/index.php.+post.+)|(https:\/\/[a-zA-Z0-9.-]+\/+images\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT