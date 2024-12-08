from dataclasses import dataclass, field, fields, MISSING
from datetime import datetime
from typing import Optional, Any
from booru_tools.plugins._base import PluginBase
from pathlib import Path
from collections import defaultdict
from copy import deepcopy

@dataclass(kw_only=True)
class InternalPlugins:
    api: Optional[PluginBase] = None
    meta: Optional[PluginBase] = None

@dataclass(kw_only=True)
class Metadata:
    data: dict = field(default_factory=dict)
    file: Optional[Path] = None

    def __getitem__(self, key: str) -> Any:
        return self.data[key]
    
    def get(self, key:Any, default:Any=None):
        return self.data.get(key, default)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Metadata":
        return cls(data=data)

def default_extra():
    return defaultdict(dict)

@dataclass(kw_only=True)
class InternalResource:
    plugins: Optional[InternalPlugins] = field(default_factory=InternalPlugins)
    metadata: Optional[Metadata] = field(default_factory=Metadata)
    _extra: Optional[defaultdict] = field(default_factory=default_extra) # This is for any extra plugin specific data that the plugin may need to retain for future actions, but doesn't fit into a regular Resource

    @classmethod
    def from_dict(cls, data: dict) -> "InternalResource":
        return cls(**data)
    
    @classmethod
    def filter_valid_keys(cls, data:dict):
        # valid_keys = {field.name for field in cls.__dataclass_fields__.values()}
        valid_keys = {field.name for field in fields(cls)}
        filtered_data = {key: value for key, value in data.items() if key in valid_keys}
        return filtered_data

    def update_attributes(self, update_object:"InternalResource") -> None:
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

            setattr(self, field.name, new_value)
    
    def create_merged_copy(self, update_object:"InternalResource") -> "InternalResource":
        self_copy = deepcopy(self)
        self_copy.update_attributes(update_object=update_object)
        return self_copy

@dataclass(kw_only=True)
class InternalTag(InternalResource):
    names: list[str]
    category: Optional[str] = ""
    implications: Optional[list["InternalTag"]] = field(default_factory=list)

    def __eq__(self, other):
        if isinstance(other, InternalTag):
            return any(item in self.names for item in other.names)
        elif isinstance(other, str):
            return other in self.names
        raise NotImplementedError

    def __str__(self):
        return self.names[0]

    def __repr__(self):
        return f"Tag(name={self.names}, category={self.category}, implications={self.implications})"
    
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

@dataclass(kw_only=True)
class InternalPost(InternalResource):
    id: int
    category: Optional[str] = ""
    description: Optional[str] = ""
    tags: Optional[list[InternalTag]] = field(default_factory=list)
    sources: Optional[list[str]] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    relations: Optional[InternalRelationship] = field(default_factory=InternalRelationship)
    safety: Optional[str] = "safe"
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