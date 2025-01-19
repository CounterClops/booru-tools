from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants, resources
from datetime import datetime
from loguru import logger
import re
import html

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
        return f"{self.URL_BASE}/index.php?page=post&s=list&tags=all"
    
    POST_CATEGORY_MAP = {
        "0": constants.TagCategory.GENERAL,
        "1": constants.TagCategory.ARTIST,
        "3": constants.TagCategory.COPYRIGHT,
        "4": constants.TagCategory.CHARACTER,
        "5": constants.TagCategory.META
    }

    POST_SAFETY_MAPPING = {
        "general": constants.Safety.SAFE,
        "g": constants.Safety.SAFE,
        "sensitive": constants.Safety.SKETCHY,
        "s": constants.Safety.SKETCHY,
        "explicit": constants.Safety.UNSAFE,
        "e": constants.Safety.UNSAFE
    }

    REQUIRE_SOURCE_CHECK = True

class GelbooruMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def __init__(self):
        self.date_format = "%a %b %d %H:%M:%S %z %Y"
        logger.debug(f"Loaded {self.__class__.__name__}")

    def get_id(self, metadata:dict) -> int:
        id:int = metadata['id']
        return id

    def get_sources(self, metadata:dict) -> list[str]:
        source:str = metadata.get("source", "")
        post_url = self.get_post_url(metadata=metadata)
        if not source:
            sources:list = [post_url]
        else:
            sources:list = source.split(" ")
            sources.append(post_url)
        return sources
    
    def get_score(self, metadata:dict) -> int:
        score:int = metadata.get("score", 0)
        return score

    def get_tags(self, metadata:dict[str, any]) -> list[resources.InternalTag]:
        all_tags:list[resources.InternalTag] = []
        tags:str = metadata.get("tags", "")

        for tag in tags.split(" "):
            unescaped_tag = html.unescape(tag)
            tag_resource = resources.InternalTag(
                names=[unescaped_tag]
            )
            all_tags.append(tag_resource)

        return all_tags

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["created_at"]
        datetime_obj:datetime = datetime.strptime(datetime_str, self.date_format)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        return self.get_created_at(metadata=metadata)

    def get_safety(self, metadata:dict) -> str:
        rating:str = metadata["rating"]
        safety:str = self.POST_SAFETY_MAPPING.get(rating.lower(), constants.Safety._DEFAULT)
        return safety

    def get_md5(self, metadata:dict) -> str:
        md5:str = metadata.get("md5", "")
        return md5

    def get_post_url(self, metadata:dict) -> str:
        post_id = self.get_id(metadata=metadata)
        url = f"{self.URL_BASE}/index.php?page=post&s=view&id={post_id}"
        return url
    
    def get_deleted(self, metadata:dict) -> bool:
        deleted:bool = metadata.get("is_deleted", False)
        return deleted

class GelbooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/.+page=post.+)|(https:\/\/[a-zA-Z0-9.-]+\/+samples\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT