from datetime import datetime
from typing import Any
import re

from booru_tools.shared import constants, resources
from booru_tools.plugins import _plugin_template

class SharedAttributes:
    _DOMAINS = [
        "furaffinity.net"
    ]
    _CATEGORY = [
        "furaffinity"
    ]
    _NAME = "furaffinity"

    URL_BASE = "https://www.furaffinity.net"

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/home"
    
    POST_CATEGORY_MAP = {}

    POST_SAFETY_MAPPING = {
        "General": constants.Safety.SAFE,
        "Mature": constants.Safety.SKETCHY,
        "Adult": constants.Safety.UNSAFE
    }

    REQUIRE_SOURCE_CHECK = True

class FurAffinityValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/view\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/art\/.+)")
    USER_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/user\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT

class FurAffinityMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def get_id(self, metadata:dict) -> int:
        id:int = metadata['id']
        return id

    def get_sources(self, metadata:dict) -> list[str]:
        sources:list[str] = []
        
        file_url = metadata.get("url")
        if file_url:
            sources.append(file_url)

        post_url = self.get_post_url(metadata=metadata)
        if post_url:
            sources.append(post_url)
        
        return sources

    def get_description(self, metadata:dict) -> str:
        description:str = metadata.get("description", "")
        return description
    
    def get_score(self, metadata:dict) -> int:
        score:int = metadata.get("favorites", 0)
        return score

    def get_tags(self, metadata:dict[str, Any]) -> list[resources.InternalTag]:
        tags:list[str] = metadata.get("tags", [])
        all_tags:list[resources.InternalTag] = []

        artist_tag:str = metadata.get("artist", "").lower()
        all_tags.append(
            resources.InternalTag(names=[artist_tag], category=constants.TagCategory.ARTIST)
        )

        try:
            tags.remove(artist_tag)
        except ValueError:
            pass

        for tag in tags:
            if tag == "Keywords":
                continue
            tag = tag.lower()
            all_tags.append(
                resources.InternalTag(names=[tag])
            )
        
        return all_tags

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["date"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        return self.get_created_at(metadata=metadata)

    def get_safety(self, metadata:dict) -> str:
        rating:str = metadata["rating"]
        safety:str = self.POST_SAFETY_MAPPING.get(rating, constants.Safety._DEFAULT)
        return safety

    def get_post_url(self, metadata:dict) -> str:
        post_id = self.get_id(metadata=metadata)
        post_url = f"{self.URL_BASE}/view/{post_id}/"
        return post_url