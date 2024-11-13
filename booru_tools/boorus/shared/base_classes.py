from dataclasses import dataclass, field

class Base():
    _DOMAINS = []
    _CATEGORY = []
    _NAME = ""

    def import_config(self, config:dict={}):
        for key, value in config.items():
            setattr(self, key, value)

@dataclass
class Post:
    source: str = None
    relations: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    safety:str = 'safe'

@dataclass
class Pool:
    id: int
    title: str
    category: str
    description: str = ""
    posts: list = field(default_factory=list)

@dataclass
class PoolPost:
    id: int
    destination_id: int
    metadata: dict
