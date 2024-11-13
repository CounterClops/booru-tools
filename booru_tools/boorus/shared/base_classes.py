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
    source_id: int
    posts: list = field(default_factory=list)

@dataclass
class PoolPost:
    source_id: int
    destination_id: int
    metadata: dict
