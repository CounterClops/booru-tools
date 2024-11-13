from .errors import *
from loguru import logger
from .base_classes import Base, Post

class CommonBooru(Base):
    def __init__(self, config:dict={}):
        logger.debug(f"Loaded {self.__class__.__name__}")
        self.safety_mapping = {
            "safe": "safe",
            "sketchy": "sketchy",
            "unsafe": "unsafe"
        }
        self.import_config(config=config)

    def get_tags(self, metadata: dict) -> list:
        tags = metadata.get("tags", [])
        return tags

    def validate_tags(self, metadata: dict) -> dict:
        tags_is_list = isinstance(metadata['tags'], list)
        tags_items_are_str = all(
            isinstance(item, str) for item in metadata['tags']
        )

        if tags_is_list and tags_items_are_str:
            return metadata
        
        metadata['tags'] = []
        return metadata
    
    def validate_tag_category(self, tag_category) -> str:
        tag_category_type = type(tag_category)
    
        if tag_category_type is not str:
            raise InvalidTagCategory
        if tag_category == "":
            raise InvalidTagCategory
        
        return tag_category

    def convert_tag_category(self, tag_category) -> str:
        tag_category_is_str = isinstance(tag_category, str)
        if tag_category_is_str:
            return tag_category
        return ""
    
    def add_tag_category_map(self, metadata: dict) -> dict:
        metadata['tag_category_map'] = {}
        return metadata
    
    def update_sources(self, metadata: dict) -> dict:
        try:
            metadata['sources']
            logger.debug(f"Found sources in {metadata['id']}")
        except KeyError:
            metadata['sources'] = [metadata['source']]
            logger.debug(f"Set source as sources in {metadata['id']}")
        
        return metadata
    
    def generate_sources_string(self, metadata:dict) -> str:
        sources_str = "\n".join(metadata.get("sources", []))
        logger.debug(f"Generated '{sources_str}' sources string for {metadata['id']}")
        return sources_str
    
    def get_safety(self, metadata: dict) -> str:
        safety = metadata.get("rating", "safe")

        try:
            safety = self.safety_mapping[safety]
        except KeyError:
            pass

        return safety

    def create_standard_post(self, metadata:dict) -> Post:
        sources = self.generate_sources_string(metadata=metadata)
        tags = self.get_tags(metadata=metadata)
        safety = self.get_safety(metadata=metadata)

        standard_post = Post(
            source=sources,
            tags=tags,
            safety=safety
        )

        return standard_post