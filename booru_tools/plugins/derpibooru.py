from loguru import logger
from datetime import datetime
import re

from booru_tools.shared import constants, resources
from booru_tools.plugins import _plugin_template

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
        "artist": constants.Category.ARTIST,
        "editor": constants.Category.CONTRIBUTOR,
        "commissioner": constants.Category.CONTRIBUTOR,
        "oc": constants.Category.CHARACTER,
        "my little pony": constants.Category.COPYRIGHT,
        "comic": constants.Category.COPYRIGHT,
        "series": constants.Category.COPYRIGHT,
        "tumblr": constants.Category.COPYRIGHT,
        "art pack": constants.Category.COPYRIGHT,
        "ship": constants.Category.LORE,
        "generator": constants.Category.META,
    }

    POST_SAFETY_MAPPING = {
        "safe": constants.Safety.SAFE,
        "questionable": constants.Safety.SKETCHY,
        "suggestive": constants.Safety.SKETCHY,
        "explicit": constants.Safety.UNSAFE,
        "semi-grimdark": constants.Safety.UNSAFE,
        "grimdark": constants.Safety.UNSAFE, 
        "grotesque": constants.Safety.UNSAFE,
    }

    REQUIRE_SOURCE_CHECK = True

class DerpibooruMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")

    def get_id(self, metadata:dict) -> int:
        id:int = metadata['id']
        return id

    def get_sources(self, metadata:dict) -> list[str]:
        source_urls:list = metadata.get("source_urls", [])
        post_url = self.get_post_url(metadata=metadata)
        sources:list = source_urls.append(post_url)
        return sources

    def get_description(self, metadata:dict) -> str:
        description:str = metadata.get("description", "")
        return description
    
    def get_score(self, metadata:dict) -> int:
        score:int = metadata.get("score", 0)
        return score

    def get_tags(self, metadata:dict[str, any]) -> list[resources.InternalTag]:
        all_tags:list[resources.InternalTag] = []
        tags:list[str] = metadata.get("tags", [])

        for tag in tags:
            tag_name, tag_category, tag_implications = self._extract_tag_info(tag)
            
            if not tag_name:
                continue

            tag_data = {
                "names": [tag_name.lower()],
                "category": tag_category,
                "implications": tag_implications
            }
            tag_resource = resources.InternalTag.from_dict(tag_data)
            all_tags.append(tag_resource)

        return all_tags

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["created_at"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        return self.get_created_at(metadata=metadata)

    def get_safety(self, metadata:dict) -> str:
        tags = metadata["tags"]
        for safety in self.POST_SAFETY_MAPPING.keys():
            if safety in tags:
                rating:str = safety
                break
        try:
            safety:str = self.POST_SAFETY_MAPPING.get(rating.lower(), constants.Safety._DEFAULT)
        except UnboundLocalError as e:
            logger.warning(f"Could not find safety rating in tags: {tags}")
            safety = constants.Safety._DEFAULT
        return safety

    def get_post_url(self, metadata:dict) -> str:
        post_id = self.get_id(metadata=metadata)
        url = f"{self.URL_BASE}/images/{post_id}"
        return url
    
    def _extract_tag_info(self, tag:str) -> list[str, str, list]:
        split_tag = tag.split(":")

        tag_implications = []
        raw_tag_category = None

        category_tag_checks = [
            split_tag[0], # Check there is something before the :
            len(tag) > 3, # Check the tag is longer than 3 characters
            len(split_tag) > 1, # Check the items in the split tag list is greater than 1
        ]

        if not all(category_tag_checks):
            tag_name = tag.replace(" ", "_").replace("__", "_")
            if tag_name == ["useless_source_url", "source needed"]:
                tag_category = constants.Category.META
            else:
                tag_category = constants.Category._DEFAULT
            return tag_name, tag_category, tag_implications
        
        raw_tag_category, tag_name = split_tag
        tag_category = self.POST_CATEGORY_MAP.get(raw_tag_category, constants.Category._DEFAULT)
        if tag_category == constants.Category._DEFAULT:
            logger.warning(f"Unknown tag category: {raw_tag_category}")
  
        tag_name = tag_name.replace(" ", "_").replace("__", "_")

        if raw_tag_category == "spoiler":
            return None, None
        elif raw_tag_category == "parent":
            tag_category = constants.Category.LORE
            tag_name = f"parent_{tag_name}"
        elif raw_tag_category == "parents":
            tag_category = constants.Category.LORE
            tag_name = f"parents_{tag_name}"
        elif raw_tag_category == "my little pony":
            tag_name = f"my_little_pony_{tag_name}"
            tag_implications.append("my_little_pony")
        elif raw_tag_category == "fusion":
            tag_implications.append(tag_name)
            tag_name = f"fusion_{tag_name}"
            tag_category = constants.Category.META
        elif raw_tag_category == "ship":
            tag_name = f"ship_{tag_name}"
            tag_category = constants.Category.META

        return tag_name, tag_category, tag_implications

class DerpibooruValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/images\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/img\/view\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT