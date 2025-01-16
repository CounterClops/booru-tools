from loguru import logger
from booru_tools.plugins import danbooru

class SharedAttributes(danbooru.SharedAttributes):
    _DOMAINS = [
        "safebooru.donmai.us"
    ]
    _CATEGORY = [
        "danbooru"
    ]
    _NAME = "danbooru_safebooru"

    URL_BASE = "https://danbooru.donmai.us"

class DanbooruSafebooruMeta(SharedAttributes, danbooru.DanbooruMeta):
    pass

class DanbooruSafebooruValidator(SharedAttributes, danbooru.DanbooruValidator):
    pass