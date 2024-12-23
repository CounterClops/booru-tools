
class SharedAttributes:
    _DOMAINS = [
        "konachan.com"
    ]
    _CATEGORY = [
        "konachan"
    ]
    _NAME = "konachan"

    URL_BASE = "https://konachan.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/post?tags="
    
    POST_CATEGORY_MAP = {}