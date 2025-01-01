from loguru import logger
from datetime import datetime
import re

from booru_tools.plugins import _plugin_template
from booru_tools.shared import constants, resources

class SharedAttributes:
    _DOMAINS = [
        "newgrounds.com"
    ]
    _CATEGORY = [
        "newgrounds"
    ]
    _NAME = "newgrounds"

    URL_BASE = "https://www.newgrounds.com"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/search/summary?terms="
    
    POST_CATEGORY_MAP = {}

    POST_SAFETY_MAPPING = {
        "g": constants.Safety.SAFE,
        "t": constants.Safety.SAFE,
        "m": constants.Safety.SKETCHY,
        "a": constants.Safety.UNSAFE
    }

class NewgroundsValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[w.]*newgrounds\.com\/portal\/view\/\d+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/(?!www\.)\w+\.newgrounds\.com)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[w.]*newgrounds\.com\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT

class NewgroundsMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def get_id(self, metadata:dict) -> int:
        id:int = metadata['index']
        return id

    def get_description(self, metadata:dict) -> str:
        description:str = metadata.get("description", "")
        return description
    
    def get_score(self, metadata:dict) -> int:
        score:int = metadata.get("favorites", 0)
        return score

    def get_tags(self, metadata:dict[str, any]) -> list[resources.InternalTag]:
        return []

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["date"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        return self.get_created_at(metadata=metadata)

    def get_relations(self, metadata:dict) -> resources.InternalRelationship:
        return resources.InternalRelationship()

    def get_safety(self, metadata:dict) -> str:
        rating:str = metadata["rating"]
        safety:str = self.POST_SAFETY_MAPPING.get(rating, constants.Safety._DEFAULT)
        return safety

    def get_md5(self, metadata:dict) -> str:
        return ""

    def get_post_url(self, metadata:dict) -> str:
        post_url:str = metadata['post_url']
        return post_url

    def get_pools(self, metadata:dict) -> list[resources.InternalPool]:
        return []