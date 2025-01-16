from loguru import logger
from booru_tools.plugins import e621

class SharedAttributes(e621.SharedAttributes):
    _DOMAINS = [
        "e926.net"
    ]
    _CATEGORY = [
        "e926"
    ]
    _NAME = "e926"

    URL_BASE = "https://e926.net"

class E926Meta(SharedAttributes, e621.E621Meta):
    pass

class E926Validator(SharedAttributes, e621.E621Validator):
    pass