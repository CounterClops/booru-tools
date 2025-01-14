from loguru import logger
from base64 import b64encode
from datetime import datetime
from pathlib import Path
from typing import Any
import aiohttp
import asyncio
import re
import json

from booru_tools.shared import resources, errors, constants
from booru_tools.plugins import _base
from booru_tools.downloaders import gallerydl

class MetadataPlugin(_base.PluginBase):
    DOWNLOAD_MANAGER = gallerydl.GalleryDlManager()

    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")

    def get_id(self, metadata:dict) -> int:
        raise NotImplementedError

    def get_sources(self, metadata:dict) -> list[str]:
        raise NotImplementedError

    def get_description(self, metadata:dict) -> str:
        raise NotImplementedError

    def get_score(self, metadata:dict) -> int:
        raise NotImplementedError

    def get_tags(self, metadata:dict) -> list[resources.InternalTag]:
        raise NotImplementedError

    def get_created_at(self, metadata:dict) -> datetime | None:
        raise NotImplementedError

    def get_updated_at(self, metadata:dict) -> datetime | None:
        raise NotImplementedError

    def get_relations(self, metadata:dict) -> resources.InternalRelationship:
        raise NotImplementedError

    def get_safety(self, metadata:dict) -> str:
        raise NotImplementedError

    def get_md5(self, metadata:dict) -> str:
        raise NotImplementedError
    
    def get_sha1(self, metadata:dict) -> str:
        raise NotImplementedError

    def get_post_url(self, metadata:dict) -> str:
        raise NotImplementedError

    def get_pools(self, metadata:dict) -> list[resources.InternalPool]:
        raise NotImplementedError
    
    def get_deleted(self, metadata:dict) -> bool:
        raise NotImplementedError

    def from_metadata_file(self, metadata_file:Path, plugins:resources.InternalPlugins=None) -> resources.InternalPost:
        with open(metadata_file) as file:
            metadata = resources.Metadata(
                data=json.load(file),
                file=metadata_file.absolute()
            )
        
        if not plugins:
            plugins = resources.InternalPlugins(
                api=None,
                meta=self
            )

        post_data = {
            "plugins": plugins,
            "metadata": metadata,
            "origin": self._NAME
        }

        metadata_attributes:dict[str, list[function, list[Any]]] = {
            "id": [self.get_id, [metadata]],
            "sources": [self.get_sources, [metadata]],
            "description": [self.get_description, [metadata]],
            "score": [self.get_score, [metadata]],
            "tags": [self.get_tags, [metadata]],
            "created_at": [self.get_created_at, [metadata]],
            "updated_at": [self.get_updated_at, [metadata]],
            "relations": [self.get_relations, [metadata]],
            "safety": [self.get_safety, [metadata]],
            "md5": [self.get_md5, [metadata]],
            "sha": [self.get_sha1, [metadata]],
            "deleted": [self.get_deleted, [metadata]],
            "post_url": [self.get_post_url, [metadata]],
            "pools": [self.get_pools, [metadata]],
        }

        for key, attributes in metadata_attributes.items():
            func, args = attributes
            try:
                post_data[key] = func(*args)
            except NotImplementedError as e:
                logger.debug(f"'{key}' not supported for '{self.__class__.__qualname__}' skipping")
        
        post = resources.InternalPost(
            **post_data
        )
        
        return post

class ValidationPlugin(_base.PluginBase):
    POST_URL_PATTERN:re.Pattern = None
    USER_URL_PATTERN:re.Pattern = None
    POOL_URL_PATTERN:re.Pattern = None
    GLOBAL_URL_PATTERN:re.Pattern = None

    def __init__(self):
        logger.debug(f"Loaded {self.__class__.__name__}")

    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN:
            if self.POST_URL_PATTERN.match(url):
                return constants.SourceTypes.POST
        if self.USER_URL_PATTERN:
            if self.USER_URL_PATTERN.match(url):
                return constants.SourceTypes.AUTHOR
        if self.POOL_URL_PATTERN:
            if self.POOL_URL_PATTERN.match(url):
                return constants.SourceTypes.POOL
        if self.GLOBAL_URL_PATTERN:
            if self.GLOBAL_URL_PATTERN.match(url):
                return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT

class ApiPlugin(_base.PluginBase):
    def __init__(self, session: aiohttp.ClientSession = None):
        logger.debug(f"Loaded {self.__class__.__name__}")
        self.session = session
        self.tmp_path = constants.TEMP_FOLDER

    @staticmethod
    def encode_auth_headers(user: str, token: str) -> str:
        """
        Encodes the authentication headers into base64

        This method encodes the authentication headers. It takes a user and a token, concatenates them with
        a colon in between, encodes the result in UTF-8, base64 encodes the result, and then decodes the result in ASCII.
        It returns the final result as a string.

        Args:
            user (str): The username.
            token (str): The token/password.

        Returns:
            str: The encoded authentication headers.
        """
        return b64encode(f'{user}:{token}'.encode()).decode('ascii')

    def create_tmp_directory(self) -> Path:
        current_time = datetime.now()
        timestamp = str(current_time.timestamp())
        download_directory = self.tmp_path / timestamp
        download_directory.mkdir(parents=True, exist_ok=True)
        return download_directory
    
    async def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        raise NotImplementedError
    
    async def find_similar_posts(self, post:resources.InternalPost) -> list[resources.InternalPost]:
        raise NotImplementedError
    
    async def find_posts_from_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalPost]:
        raise NotImplementedError
    
    async def find_exact_tag(self, tag:resources.InternalTag) -> resources.InternalTag | None:
        raise NotImplementedError
    
    async def get_all_tags(self, treat_aliases_as_implications:bool=False) -> list[resources.InternalTag]:
        raise NotImplementedError
    
    async def get_all_pools(self) -> list[resources.InternalPool]:
        raise NotImplementedError
    
    async def get_all_posts(self) -> list[resources.InternalPost]:
        raise NotImplementedError

    async def push_tag(self, tag:resources.InternalTag, replace_tags:bool=False, create_empty_tags:bool=True) -> resources.InternalTag:
        raise NotImplementedError

    async def push_post(self, post:resources.InternalPost) -> resources.InternalPost:
        raise NotImplementedError

    async def push_pool(self, pool:resources.InternalPool) -> resources.InternalPool:
        raise NotImplementedError