import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants

class SharedAttributes:
    _DOMAINS = [
        "rule34vault.com"
    ]
    _CATEGORY = [
        "rule34vault"
    ]
    _NAME = "rule34vault"

    URL_BASE = "https://rule34vault.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/"
    
    POST_CATEGORY_MAP = {}

class Rule34VaultValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/post\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/posts\/[0-9]*\/[0-9]*\/.*)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT