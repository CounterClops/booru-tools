import re

from loguru import logger
from booru_tools.plugins import _plugin_template, gelbooru
from booru_tools.shared import constants
from booru_tools.downloaders import gallerydl

class SharedAttributes:
    _DOMAINS = [
        "rule34.xxx"
    ]
    _CATEGORY = [
        "rule34"
    ]
    _NAME = "rule34"

    URL_BASE = "https://rule34.xxx"

    api_key:str = None
    user_id:str = None
    requests_per_minute:int = None

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/index.php?page=dapi&s=post&q=index"

    @property
    def DOWNLOAD_MANAGER(self):
        try:
            return self._downloader
        except (AttributeError, NotImplementedError):
            logger.debug("Creating a new downloader")

        extra_args = []

        if self.api_key and self.user_id:
            extra_args.extend([
                "-o", f"api-key={self.api_key}",
                "-o", f"user-id={self.user_id}",
            ])

        if self.requests_per_minute:
            sleep_seconds = 60.0 / self.requests_per_minute
            extra_args.extend(["-o", f"sleep-request={sleep_seconds}"])

        self._downloader = gallerydl.GalleryDlManager(
            extractor="gelbooru_v02",
            extra_params=extra_args
        )
        return self._downloader

class Rule34XxxMeta(SharedAttributes, gelbooru.GelbooruMeta):
    pass

class Rule34XxxValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/index.php.+post.+)|(https:\/\/[a-zA-Z0-9.-]+\/+images\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT