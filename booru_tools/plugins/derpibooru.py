from booru_tools.shared import constants

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