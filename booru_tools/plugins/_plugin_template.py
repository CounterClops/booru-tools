from loguru import logger
from base64 import b64encode
from datetime import datetime
from pathlib import Path
import aiohttp
import asyncio
import re

from booru_tools.shared import resources, errors, constants
from booru_tools.plugins import _base

class MetadataPlugin(_base.PluginBase):
    def get_id(metadata:dict) -> int:
        raise NotImplementedError

    def get_sources(metadata:dict) -> list[str]:
        raise NotImplementedError

    def get_description(metadata:dict) -> str:
        raise NotImplementedError

    def get_tags(metadata:dict) -> list[resources.InternalTag]:
        raise NotImplementedError

    def get_created_at(metadata:dict) -> datetime | None:
        raise NotImplementedError

    def get_updated_at(metadata:dict) -> datetime | None:
        raise NotImplementedError

    def get_relations(metadata:dict) -> resources.InternalRelationship:
        raise NotImplementedError

    def get_safety(metadata:dict) -> str:
        raise NotImplementedError

    def get_md5(metadata:dict) -> str:
        raise NotImplementedError

    def get_post_url(metadata:dict) -> str:
        raise NotImplementedError

    def get_pools(metadata:dict) -> list[resources.InternalPool]:
        raise NotImplementedError

class ValidationPlugin(_base.PluginBase):
    POST_URL_PATTERN:re.Pattern = None
    USER_URL_PATTERN:re.Pattern = None
    POOL_URL_PATTERN:re.Pattern = None
    GLOBAL_URL_PATTERN:re.Pattern = None

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
        self.tmp_path = Path("tmp")

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
        return download_directory
    
    async def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        raise NotImplementedError
    
    async def find_similar_posts(self, post:resources.InternalPost) -> list[resources.InternalPost]:
        raise NotImplementedError
    
    async def find_posts_from_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalPost]:
        raise NotImplementedError
    
    async def find_exact_tag(self, tag:resources.InternalTag) -> resources.InternalTag | None:
        raise NotImplementedError
    
    async def get_all_tags(self) -> list[resources.InternalTag]:
        raise NotImplementedError
    
    async def get_all_pools(self) -> list[resources.InternalPool]:
        raise NotImplementedError
    
    async def get_all_posts(self) -> list[resources.InternalPost]:
        raise NotImplementedError

    async def push_tag(self, tag:resources.InternalTag) -> resources.InternalTag:
        raise NotImplementedError

    async def push_post(self, post:resources.InternalPost) -> resources.InternalPost:
        raise NotImplementedError

    async def push_pool(self, pool:resources.InternalPool) -> resources.InternalPool:
        raise NotImplementedError