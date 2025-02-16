from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
from collections import defaultdict
from http.cookiejar import MozillaCookieJar
import json
import shutil
import hashlib
import asyncio
import aiohttp
import signal

from booru_tools.loaders import plugin_loader
from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, resources, constants, config

class GracefulExit(SystemExit):
    code = 1

class SessionManager:
    def __init__(self, limit_per_host:int=10):
        self.session = None
        self.limit_per_host = limit_per_host
        self.default_headers = {
            "User-Agent": "BooruTools/1.0"
        }
        self.cookies = {}

    def start(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            limit_per_host=self.limit_per_host
        )
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.default_headers,
                skip_auto_headers=self.default_headers.keys(),
                connector=connector,
                cookies=self.cookies
            )
        return self.session

    async def close(self):
        logger.debug("Closing aiohttp session")
        await self.session.close()

    def load_cookies(self, cookies:dict) -> None:
        self.cookies = cookies

        if not self.session.closed:
            logger.debug(f"Updating session cookies with {len(cookies)} cookies")
            self.session.cookie_jar.update_cookies(cookies)
    
    def load_cookie_file(self, cookie_file:Path) -> dict:
        cookies = {}

        if not cookie_file.exists():
            raise FileNotFoundError(f"Cookie file '{cookie_file}' does not exist")
        
        cookie_file = Path(cookie_file)

        if cookie_file.suffix == ".txt":
            logger.debug(f"Loading cookies from '{cookie_file}' with MozillaCookieJar")
            cookie_jar = MozillaCookieJar()
            cookie_jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
            for cookie in cookie_jar:
                cookies[cookie.name] = cookie.value
        elif cookie_file.suffix == ".json":
            logger.debug(f"Loading cookies from '{cookie_file}' with json")
            with open(cookie_file, "r") as f:
                cookies = json.load(f)
        else:
            raise ValueError("Unsupported file format. Only .txt and .json are supported.")

        self.load_cookies(cookies)
        return cookies

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="", tmp_path:str="tmp"):
        if not booru_plugin_directory:
            program_path = constants.ROOT_FOLDER
            self.booru_plugin_directory = program_path / Path("plugins")
        else:
            self.booru_plugin_directory = Path(booru_plugin_directory)
        
        self.config = config.ConfigManager()
        self.tmp_directory = constants.TEMP_FOLDER
        self.session_manager = SessionManager(
            limit_per_host=self.config["networking"].get("limit_per_host", 20)
        )

        signal.signal(signal.SIGINT, self.raise_graceful_exit)
        signal.signal(signal.SIGTERM, self.raise_graceful_exit)

        try:
            self.session_manager.start()
            cookie_file = self.config["networking"]["cookies_file"]
            if cookie_file:
                logger.debug(f"Attempting to load cookies from '{cookie_file}'")
                self.session_manager.load_cookie_file(
                    cookie_file=cookie_file
                )
        except RuntimeError as e:
            logger.debug(f"Error starting session due to {e}")
        self.load_plugins()

    def raise_graceful_exit(self, *args):
        try:
            loop = asyncio.get_event_loop()
            logger.debug("Cancelling all async tasks")
            for task in asyncio.all_tasks():
                task.cancel()
            close_session_task = loop.create_task(self.session_manager.close())
            loop.run_until_complete(close_session_task)
            loop.stop()
        except RuntimeError:
            logger.debug("No async loop")
        self.cleanup_process_directories()
        logger.info("Gracefully shutdown")
        raise GracefulExit()
    
    # def setup_logger(self) -> None:
    #     logger.configure()

    def load_plugins(self) -> None:
        """Loads the plugins for this instances set of loaders
        """
        self.metadata_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.MetadataPlugin
        )
        self.metadata_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        self.api_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.ApiPlugin,
            session=self.session_manager.session
        )
        self.api_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        self.validation_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.ValidationPlugin
        )
        self.validation_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        destination = self.config["core"]["destination"]
        if destination:
            self.destination_plugin:_plugin_template.ApiPlugin = self.api_loader.load_matching_plugin(domain=destination, category=destination)
    
    async def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        logger.info(f"Getting exact post for '{post.id}'")

        if post.post_url not in post.sources:
            logger.debug(f"Adding post url '{post.post_url}' to sources for '{post.id}'")
            post.sources.append(post.post_url)

        exact_post = await self.destination_plugin.find_exact_post(post=post)
        return exact_post

    async def update_posts(self, posts:list[resources.InternalPost]):
        logger.info(f"Updating {len(posts)} posts")

        tasks:list[asyncio.Task] = []
        async with asyncio.TaskGroup() as task_group:
            for post in posts:
                if not post.local_file:
                    logger.debug(f"No file to upload for '{post.id}'")
                else:
                    logger.debug(f"File '{post.local_file.name}' found for '{post.id}'")
                    post = self.add_missing_post_hashes(post=post)

                if post.post_url:
                    if post.post_url not in post.sources:
                        logger.debug(f"Updating post ({post.id}) sources with '{post.post_url}'")
                        post.sources.append(post.post_url)

                logger.debug(f"Updating post '{post.id}'")
                task = task_group.create_task(
                    self.destination_plugin.push_post(post=post)
                )
                tasks.append(task)
        results = [task.result() for task in tasks]

    def check_post_allowed(self, post:resources.InternalPost):
        blacklisted_tags = self.config["core"]["blacklisted_tags"]
        if post.contains_any_tags(tags=blacklisted_tags):
            logger.debug(f"Post '{post.id}' contains blacklisted tags from {blacklisted_tags}")
            return False
        required_tags = self.config["core"]["required_tags"]
        if not post.contains_all_tags(tags=required_tags):
            logger.debug(f"Post '{post.id}' does not contain all required tags from {required_tags}")
            return False
        allowed_safety = self.config["core"]["allowed_safety"]
        if allowed_safety and (post.safety not in allowed_safety):
            logger.debug(f"Post '{post.id}' with '{post.safety}' is not in the allowed safety selection from {allowed_safety}")
            return False
        minimum_score = self.config["core"]["minimum_score"]
        if minimum_score and post.score < minimum_score:
            logger.debug(f"Post '{post.id}' has a score of {post.score} which is below the minimum score of {minimum_score}")
            return False
        if post.deleted:
            logger.debug(f"Post '{post.id}' is marked as deleted")
            return False
        logger.debug(f"Post '{post.id}' passed all checks")
        return True

    async def update_tags(self, tags:list[resources.InternalTag]):
        logger.info(f"Updating {len(tags)} tags")
        chunk_count = 0
        chunk_size = 500
        total_tags = len(tags)
        for tags_chunk in self.divide_chunks(tags, chunk_size):
            chunk_count += 1
            completion_percent = int(((chunk_count * chunk_size) / total_tags) * 100)
            logger.info(f"Processing chunk {chunk_count} ({len(tags_chunk)}/{chunk_size}) of {total_tags} tags ({completion_percent}%)")
            tasks:list[asyncio.Task] = []
            async with asyncio.TaskGroup() as task_group:
                for tag in tags_chunk:
                    task = task_group.create_task(
                        self.destination_plugin.push_tag(tag=tag)
                    )
                    tasks.append(task)
            results = [task.result() for task in tasks]
    
    def cleanup_process_directories(self) -> None:
        """Cleans up the temporary directories
        """
        directories_to_delete:list[Path] = [
            self.tmp_directory
        ]

        for directory in directories_to_delete:
            self.delete_directory(directory=directory)
        return None
    
    def delete_directory(self, directory:Path) -> None:
        """Deletes the provided directory

        Args:
            directory (Path): The directory to delete
        """
        logger.debug(f"Deleting '{directory}' folder")
        shutil.rmtree(directory)
    
    def add_missing_post_hashes(self, post:resources.InternalPost) -> resources.InternalPost:
        file_md5 = self.get_md5_hash(file_path=post.local_file)
        file_sha1 = self.get_sha1_hash(file_path=post.local_file)

        if post.md5 != file_md5:
            if post.md5:
                logger.warning(f"Post '{post.id}' md5 hash '{post.md5}' is different from file md5 hash '{file_md5}'")
            logger.debug(f"Updating post '{post.id}' md5 hash from '{post.md5}' to '{file_md5}'")
            post.md5 = file_md5
        if post.sha1 != file_sha1:
            if post.sha1:
                logger.warning(f"Post '{post.id}' sha1 hash '{post.sha1}' is different from file sha1 hash '{file_sha1}'")
            logger.debug(f"Updating post '{post.id}' sha1 hash from '{post.sha1}' to '{file_sha1}'")
            post.sha1 = file_sha1
        
        return post

    @staticmethod
    def get_md5_hash(file_path:Path) -> str:
        if not file_path.exists():
            return ""
        
        logger.debug(f"Calculating md5 hash for '{file_path}'")
        with open(file_path, "rb") as file:
            file_hash = hashlib.md5()
            while chunk := file.read(8192):
                file_hash.update(chunk)

        md5_hash = file_hash.hexdigest()
        logger.debug(f"MD5 hash for '{file_path}' is '{md5_hash}'")
        return md5_hash

    @staticmethod
    def get_sha1_hash(file_path:Path) -> str:
        if not file_path.exists():
            return ""
        
        logger.debug(f"Calculating sha1 hash for '{file_path}'")
        with open(file_path, "rb") as file:
            file_hash = hashlib.sha1()
            while chunk := file.read(8192):
                file_hash.update(chunk)

        sha1_hash = file_hash.hexdigest()
        logger.debug(f"SHA1 hash for '{file_path}' is '{sha1_hash}'")
        return sha1_hash

    @staticmethod
    def split_tag_list(tag_string:str, and_seperator:str="|", or_seperator:str=","):
        tags = []
        comma_split_tags = [tag for tag in tag_string.split(or_seperator) if tag != ""]
        for tag in comma_split_tags:
            if and_seperator in tag:
                and_tags = tag.split(and_seperator)
                tags.append(and_tags)
            else:
                tags.append(tag)
        return tags
    
    @staticmethod
    def divide_chunks(array:list, max_size:int):
        for i in range(0, len(array), max_size): 
            yield array[i:i + max_size]
    
    def override_plugin_config(self, plugin:object, plugin_override:str=""):
        override_pairs = plugin_override.split(",")
        for pair in override_pairs:
            key, value = pair.split("=")
            setattr(plugin, key, value)