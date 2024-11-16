from dataclasses import dataclass, field
from typing import Optional

from api_client import ApiClient
from meta import CommonBooru

class Base():
    _DOMAINS = []
    _CATEGORY = []
    _NAME = ""

    def import_config(self, config:dict={}):
        for key, value in config.items():
            setattr(self, key, value)

@dataclass
class Resource:
    metadata_plugin: Optional[CommonBooru] = None
    api_plugin: Optional[ApiClient] = None
    metadata: Optional[dict] = {}

    # https://medium.com/@thoroc/python-data-validation-using-dataclasses-29f0cb38bbc8
    # Look into factory functions that do the conversion

@dataclass
class Post(Resource):
    source: str = None
    relations: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    safety: str = 'safe'

@dataclass
class Pool(Resource):
    id: int
    title: str
    category: str
    description: str = ""
    posts: list = field(default_factory=list)

@dataclass
class PoolPost(Resource):
    id: int
    destination_id: int
