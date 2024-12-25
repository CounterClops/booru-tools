from dataclasses import dataclass, field, fields, MISSING, InitVar
from datetime import datetime
from typing import Optional, Any
from pathlib import Path
from collections import defaultdict
from copy import deepcopy
from urllib.parse import urlparse
from loguru import logger

from booru_tools.plugins._base import PluginBase
from booru_tools.shared import constants

class UniqueList(list):
    def append(self, item):
        if item not in self:
            super().append(item)

    def extend(self, items):
        for item in items:
            self.append(item)

@dataclass(kw_only=True)
class InternalPlugins:
    api: PluginBase = None # This is the api plugin
    meta: PluginBase = None # This is the metadata plugin
    validators: list[PluginBase] = field(default_factory=list)

    def find_matching_validator(self, domain:str) -> PluginBase|None:
        for validator_plugin in self.validators:
            try:
                validator_domain_matches = any(validator_domain in domain for validator_domain in validator_plugin._DOMAINS)
                if validator_domain_matches:
                    return validator_plugin
            except Exception as e:
                logger.warning(f"Error finding validator plugin for domain '{domain}' due to {e}. Was checking against {validator_plugin._NAME} with ({validator_plugin._DOMAINS})")
        return None

@dataclass(kw_only=True)
class Metadata:
    data: dict = field(default_factory=dict) # This is the raw metadata dict
    file: Path = None # This is the path to the metadata file the metadata was pulled from

    def __getitem__(self, key: str) -> Any:
        return self.data[key]
    
    def get(self, key:Any, default:Any=None):
        return self.data.get(key, default)
    
    def items(self, *args, **kwargs):
        return self.data.items(*args, **kwargs)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Metadata":
        return cls(data=data)

def default_extra():
    return defaultdict(dict)

@dataclass(kw_only=True)
class InternalResource:
    origin: Optional[str] = None # This is the origin field of where this resource was pulled from, what source site/plugin was this created from?
    plugins: Optional[InternalPlugins] = field(default_factory=InternalPlugins) # The plugins object containing the appropriate metadata/api plugins
    metadata: Optional[Metadata] = field(default_factory=Metadata) # The metadata object containing the raw metadata and file location
    _extra: Optional[defaultdict] = field(default_factory=default_extra) # This is for any extra plugin specific data that the plugin may need to retain for future actions, but doesn't fit into a regular Resource

    @classmethod
    def from_dict(cls, data: dict) -> "InternalResource":
        return cls(**data)
    
    @classmethod
    def filter_valid_keys(cls, data:dict):
        valid_keys = {field.name for field in fields(cls)}
        filtered_data = {key: value for key, value in data.items() if key in valid_keys}
        return filtered_data

    def update_attributes(self, update_object:"InternalResource", allow_blank_values:bool=False) -> None:
        """Updates the object with the provided objects attributes, ignores default values and base fields

        Args:
            update_object (InternalResource): The new object to replace attributes in the source with
        """
        for field in fields(update_object):
            new_value = getattr(update_object, field.name)
            
            # Skip updating if the source value matches the default value
            if field.default is not MISSING and new_value == field.default:
                continue
            if field.default_factory is not MISSING and new_value == field.default_factory():
                continue
            if field.name in ["plugins", "metadata", "_extra"]:
                continue

            if not allow_blank_values:
                if not new_value:
                    continue

            setattr(self, field.name, new_value)
    
    def create_merged_copy(self, update_object:"InternalResource", allow_blank_values:bool=False) -> "InternalResource":
        self_copy = deepcopy(self)
        self_copy.update_attributes(update_object=update_object, allow_blank_values=allow_blank_values)
        return self_copy
    
    def diff(self, resource:"InternalResource", fields_to_ignore:list=[]) -> dict:
        diff = {}
        ignored_fields = self._default_diff_ignored_fields + fields_to_ignore
        for field in fields(self):
            if field.name in ignored_fields:
                continue
            self_value = getattr(self, field.name)
            other_value = getattr(resource, field.name)
            if self_value != other_value:
                if isinstance(self_value, list):
                    dif_value = [item for item in self_value if item not in other_value]
                    if not dif_value:
                        continue
                elif isinstance(self_value, dict):
                    dif_value = {key: value for key, value in self_value.items() if value != other_value.get(key)}
                    if not dif_value:
                        continue
                else:
                    dif_value = self_value
                diff[field.name] = dif_value
        return diff
    
    @property
    def _default_diff_ignored_fields(self):
        return ["plugins", "metadata", "_extra"]

@dataclass(kw_only=True)
class InternalTag(InternalResource):
    names: list[str] # The list of names for this tag
    category: Optional[str] = "" # The tag category string
    implications: Optional[list["InternalTag"]] = field(default_factory=list) # A list of all tags this specific tag implies.

    def __eq__(self, other):
        if isinstance(other, InternalTag):
            return any(item in self.names for item in other.names)
        elif isinstance(other, str):
            return other in self.names
        raise NotImplementedError

    def __str__(self):
        return self.names[0]

    def __repr__(self):
        return f"InternalTag(name={self.names}, category={self.category}, implications={self.implications})"
    
    def all_tag_strings(self) -> list[str]:
        tag_strings = set(self.names)
        for tag in self.implications:
            tag_strings.update(tag.names)
        return list(tag_strings)
    
    @classmethod
    def from_dict(cls, data: dict) -> "InternalTag":
        data = cls.filter_valid_keys(data=data)
        if 'implications' in data and data['implications']:
            tag_implications:list[InternalResource] = []
            for tag in  data['implications']:
                if isinstance(tag, str):
                    tag_implications.append(InternalTag(names=[tag]))
                elif isinstance(tag, list):
                    tag_implications.append(InternalTag(names=tag))
                elif isinstance(tag, InternalTag):
                    tag_implications.append(tag)
            data['implications'] = tag_implications

        return cls(**data)

@dataclass(kw_only=True)
class InternalRelationship:
    parent_id: Optional[int] = None
    children: Optional[list[int]] = field(default_factory=list)

    @property
    def related_post_ids(self) -> list[int]:
        related_posts = self.children
        if self.parent_id:
            related_posts.append(self.parent_id)
        return related_posts

@dataclass(kw_only=True)
class InternalPost(InternalResource):
    id: int
    category: Optional[str] = ""
    description: Optional[str] = ""
    tags: Optional[list[InternalTag]] = field(default_factory=list)
    sources: InitVar[list[str]] = field(default_factory=UniqueList)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    relations: Optional[InternalRelationship] = field(default_factory=InternalRelationship)
    safety: Optional[str] = constants.Safety._DEFAULT
    sha1: Optional[str] = ""
    md5: Optional[str] = ""
    post_url: Optional[str] = ""
    pools: Optional[list["InternalPool"]] = field(default_factory=list)
    local_file: Optional[Path] = None

    def __eq__(self, other):
        if isinstance(other, InternalPost):
            id_matches = self.id == other.id
            category_matches = self.category == other.category
            return id_matches and category_matches
        elif isinstance(other, str):
            return self.id == other
        return NotImplementedError

    def __post_init__(self, sources):
        if not sources:
            self.sources = []
        self.sources = sources
    
    @property
    def _default_diff_ignored_fields(self):
        return ["plugins", "metadata", "_extra", "relations"]

    @property
    def sources(self) -> list:
        return self._sources

    @sources.setter
    def sources(self, value):
        self._sources = UniqueList(set(value))

    def sources_of_type(self, desired_source_type:str) -> list[str]:
        found_sources = []
        for source in self.sources:
            source_domain = urlparse(url=source).hostname
            validator_plugin = self.plugins.find_matching_validator(domain=source_domain)

            if not validator_plugin:
                continue

            source_type = validator_plugin.get_source_type(url=source)
            if source_type == desired_source_type:
                found_sources.append(source)
        
        return found_sources
    
    def contains_any_tags(self, tags:list[str|InternalTag]) -> bool:
        post_tags = set(self.str_tags)
        for tag in tags:
            if isinstance(tag, str):
                if tag in post_tags:
                    logger.debug(f"Post '{self.id}' contains tags from {tags}")
                    return True
            elif isinstance(tag, InternalTag):
                tag_strings = set(tag.all_tag_strings())
                if post_tags.intersection(tag_strings):
                    logger.debug(f"Post '{self.id}' contains tags from {tags}")
                    return True
        return False
    
    def contains_all_tags(self, tags:list[str|InternalTag]) -> bool:
        post_tags = set(self.str_tags)
        required_tags = set()
        for tag in tags:
            if isinstance(tag, InternalTag):
                tag_strings = set(tag.all_tag_strings())
                required_tags.update(tag_strings)
            else:
                required_tags.add(tag)
        
        contains_all_tags =  all(required_tag in post_tags for required_tag in required_tags)
        if contains_all_tags:
            logger.debug(f"Post '{self.id}' contains all required tags from {tags}")
            return True
        return False
    
    @property
    def str_tags(self) -> list[str]:
        tag_strings = set()
        for tag in self.tags:
            names = set(tag.names)
            tag_strings.update(names)
        return list(tag_strings)
    
    @classmethod
    def from_dict(cls, data: dict) -> "InternalPost":
        data = cls.filter_valid_keys(data=data)
        if 'tags' in data and data['tags']:
            data['tags'] = [InternalTag.from_dict(tag) for tag in data['tags']]
        if 'pools' in data and data['pools']:
            data['pools'] = [InternalPool.from_dict(pool) for pool in data['pools']]
        return cls(**data)

@dataclass(kw_only=True)
class InternalPool(InternalResource):
    id: int
    names: Optional[list[str]] = field(default_factory=list)
    category: Optional[str] = ""
    description: Optional[str] = ""
    posts: Optional[list[InternalPost]] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __eq__(self, other):
        if isinstance(other, InternalPost):
            id_matches = self.id == other.id
            category_matches = self.category == other.category
            return id_matches and category_matches
        elif isinstance(other, str):
            return self.id == other
        return NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> "InternalPool":
        data = cls.filter_valid_keys(data=data)
        if 'posts' in data and data['posts']:
            data['posts'] = [InternalPost.from_dict(post) for post in data['posts']]
        return cls(**data)