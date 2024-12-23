from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants
from loguru import logger

class SharedAttributes:
    _DOMAINS = [
        "danbooru.donmai.us"
    ]
    _CATEGORY = [
        "danbooru"
    ]
    _NAME = "danbooru"

    URL_BASE = "https://danbooru.donmai.us"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/posts?tags="
    
    POST_CATEGORY_MAP = {
        "0": constants.Category.GENERAL,
        "1": constants.Category.ARTIST,
        "3": constants.Category.COPYRIGHT,
        "4": constants.Category.CHARACTER,
        "5": constants.Category.META
    }

class DanbooruMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")
    
    @property
    def allowed_tag_categories(self):
        categories = self.POST_CATEGORY_MAP.values()
        return categories

    def convert_tag_category(self, tag_category:int) -> str:
        if isinstance(tag_category, int):
            try:
                return self.POST_CATEGORY_MAP[tag_category]
            except KeyError:
                raise errors.InvalidTagCategory
    
    def validate_tag_category(self, tag_category) -> str:
        """Validate that the tag category is allowed

        Args:
            tag_category (Any): The tag category you'd like to validate

        Raises:
            errors.InvalidTagCategory: The tag category is invalid

        Returns:
            str: The valid tag category
        """
        if tag_category in self.allowed_tag_categories:
            return tag_category
        raise errors.InvalidTagCategory

    def add_tag_category_map(self, metadata: dict) -> dict:
        tag_category_map = {}
        for key in metadata.keys():
            if "tags_" not in key:
                continue
            
            category = key.replace("tags_", "")
            try:
                category = self.validate_tag_category(category)
            except errors.InvalidTagCategory:
                continue

            for tag in metadata[key]:
                tag_category_map[tag] = category
        
        metadata['tag_category_map'] = tag_category_map
        return metadata

    def generate_post_url(self, metadata:dict) -> str:
        post_id = metadata['id']
        url = f"{self.URL_BASE}/posts/{post_id}"
        return url