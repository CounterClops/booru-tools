
class SharedAttributes:
    _DOMAINS = [
        "chan.sankakucomplex.com",
        "sankakucomplex.com"
    ]
    _CATEGORY = [
        "sankaku"
    ]
    _NAME = "sankaku"

    URL_BASE = "https://chan.sankakucomplex.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/?tags="
    
    POST_CATEGORY_MAP = {}