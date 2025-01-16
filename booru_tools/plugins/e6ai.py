from loguru import logger
from booru_tools.plugins import e621

class SharedAttributes(e621.SharedAttributes):
    _DOMAINS = [
        "e6ai.net"
    ]
    _CATEGORY = [
        "e9ai"
    ]
    _NAME = "e6AI"

    URL_BASE = "https://e6ai.net"

class E6aiMeta(SharedAttributes, e621.E621Meta):
    pass

class E6aiValidator(SharedAttributes, e621.E621Validator):
    pass