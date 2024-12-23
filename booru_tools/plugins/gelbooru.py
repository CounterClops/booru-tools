
class SharedAttributes:
    _DOMAINS = [
        "gelbooru.com"
    ]
    _CATEGORY = [
        "gelbooru"
    ]
    _NAME = "gelbooru"

    URL_BASE = "https://gelbooru.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=post&s=list&tags="
    
    POST_CATEGORY_MAP = {}