from loguru import logger
import re
from datetime import datetime

from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants, resources

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

    POST_SAFETY_MAPPING = {
        "safe": constants.Safety.SAFE,
        "s": constants.Safety.SAFE,
        "questionable": constants.Safety.SKETCHY,
        "q": constants.Safety.SKETCHY,
        "explicit": constants.Safety.UNSAFE,
        "e": constants.Safety.UNSAFE
    }

class DanbooruMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")

    def get_id(self, metadata:dict) -> int:
        id:int = metadata['id']
        return id

    def get_sources(self, metadata:dict) -> list[str]:
        source:int = metadata.get("source", "")
        if not source:
            sources:list = []
        else:
            sources:list = [source]
        return sources

    def get_description(self, metadata:dict) -> str:
        description:str = metadata.get("description", "")
        return description

    def get_tags(self, metadata:dict[str, any]) -> list[resources.InternalTag]:
        all_tags:list[resources.InternalTag] = []

        for key, value in metadata.items():
            if not key.startswith("tags_"):
                continue
            if not value:
                continue
            logger.debug(f"Found tag string {key}")
            category = key.replace("tags_", "")
            for tag in value:
                tag = resources.InternalTag(
                    names=[tag],
                    category=category
                )
                all_tags.append(tag)
        
        logger.debug(f"Found {len(all_tags)} tags")
        return all_tags

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["created_at"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["updated_at"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_relations(self, metadata:dict) -> resources.InternalRelationship:
        return resources.InternalRelationship()

    def get_safety(self, metadata:dict) -> str:
        rating:str = metadata["rating"]
        safety:str = self.POST_SAFETY_MAPPING.get(rating, constants.Safety._DEFAULT)
        return safety

    def get_md5(self, metadata:dict) -> str:
        md5:str = metadata.get("md5", "")
        return md5

    def get_post_url(self, metadata:dict) -> str:
        post_id = self.get_id(metadata=metadata)
        url = f"{self.URL_BASE}/posts/{post_id}"
        return url

    def get_pools(self, metadata:dict) -> list[resources.InternalPool]:
        return []

class DanbooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/posts\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/sample\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/original\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT