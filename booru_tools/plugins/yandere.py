
class SharedAttributes:
    _DOMAINS = [
        "yande.re"
    ]
    _CATEGORY = [
        "yandere"
    ]
    _NAME = "yandere"

    URL_BASE = "https://yande.re"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/post?tags="
    
    POST_CATEGORY_MAP = {}