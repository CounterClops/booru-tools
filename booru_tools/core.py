from pathlib import Path
from loguru import logger
from http.cookiejar import MozillaCookieJar
from typing import Generator
import json
import shutil
import hashlib
import asyncio
import aiohttp
import signal
import traceback

from booru_tools.loaders import plugin_loader
from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, resources, constants, config
from booru_tools.tools.ffmpeg import FFmpeg

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
                cookies=self.cookies,
                raise_for_status=True
            )
        return self.session

    async def close(self):
        logger.debug("Closing aiohttp session")
        await self.session.close()

    def load_cookies(self, cookies:dict) -> None:
        """Update the session cookies with the provided cookies dictionary

        Args:
            cookies (dict): The cookies to update the HTTP session with
        """
        self.cookies = cookies

        if not self.session.closed:
            logger.debug(f"Updating session cookies with {len(cookies)} cookies")
            self.session.cookie_jar.update_cookies(cookies)
    
    def load_cookie_file(self, cookie_file:Path) -> dict:
        """The HTTP cookies to load from the provided file

        Args:
            cookie_file (Path): The HTTP cookies file to load

        Raises:
            FileNotFoundError: The provided cookie file does not exist
            ValueError: The provided cookie file was in an unsupported format

        Returns:
            dict: The cookies loaded from the file as a dictionary
        """
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
        
        self.config = config.shared_config_manager
        self.tmp_directory = constants.TEMP_FOLDER

        self.cleanup_temp_directories = self.config["core"]["cleanup_temp_directories"]

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
        """Raises a graceful exit exception to shutdown the program

        Raises:
            GracefulExit: The exception to raise to shutdown the program
        """
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
        """Finds the exact post from the destination site if present

        Args:
            post (resources.InternalPost): The post resource to use when searching

        Returns:
            resources.InternalPost | None: The exact post if found, otherwise None
        """
        logger.info(f"Getting exact post for '{post.id}'")

        if post.post_url not in post.sources:
            logger.debug(f"Adding post url '{post.post_url}' to sources for '{post.id}'")
            post.sources.append(post.post_url)

        exact_post = await self.destination_plugin.find_exact_post(post=post)
        return exact_post

    async def update_posts(self, posts:list[resources.InternalPost]) -> None:
        """Updates or creates the posts on the destination site

        Args:
            posts (list[resources.InternalPost]): The list of posts to update/create
        """
        logger.info(f"Updating {len(posts)} posts")
        found_tags = []
        for posts_chunk in self.divide_chunks(posts, max_size=20):
            tasks:list[asyncio.Task] = []
            posts_chunk:list[resources.InternalPost]
            async with asyncio.TaskGroup() as task_group:
                for post in posts_chunk:
                    if not post.local_file:
                        logger.debug(f"No file to upload for '{post.id}'")
                    else:
                        logger.debug(f"File '{post.local_file.name}' found for '{post.id}'")
                        post = self.add_missing_post_hashes(post=post)
                    
                    if self.config["core"]["add_video_metatags"]:
                        try:
                            post = FFmpeg.add_video_tags(post=post)
                        except Exception as e:
                            logger.error(f"Error adding video tags to '{post.id}' with {e}")
                            logger.trace(traceback.format_exc())

                    if post.post_url:
                        if post.post_url not in post.sources:
                            logger.debug(f"Updating post ({post.id}) sources with '{post.post_url}'")
                            post.sources.append(post.post_url)
                    
                    for source in post.sources:
                        if self.destination_plugin.URL_BASE in source:
                            logger.debug(f"Removing source '{source}' as its for the destination site '{self.destination_plugin.URL_BASE}'")
                            post.sources.pop(post.sources.index(source))

                    if post.tags:
                        found_tags.extend(post.tags)

                    logger.debug(f"Updating post '{post.id}'")
                    task = task_group.create_task(
                        self.destination_plugin.push_post(post=post)
                    )
                    tasks.append(task)
            results = [task.result() for task in tasks]
        
        filtered_tags = self.filter_tags(tags=found_tags)
        
        if not filtered_tags:
            logger.debug("No tags require potential updating")
            return None
        
        if not self.config["core"]["update_tag_categories"]:
            logger.info("Tag category updates disabled, skipping")
            return None
        
        logger.info(f"Updating tags for {len(filtered_tags)} tags")
        await self.update_tags(tags=filtered_tags)
        return None

    def check_post_allowed(self, post:resources.InternalPost) -> bool:
        """Check if the provided post resource meets the requirements to be uploaded

        Args:
            post (resources.InternalPost): The post resource to check if allowed

        Returns:
            bool: Whether the post is allowed to be uploaded
        """
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
        """The tags to push to the destination site

        Args:
            tags (list[resources.InternalTag]): The list of tags to push to the destination site
        """
        logger.info(f"Updating {len(tags)} tags")
        for tags_chunk in self.divide_chunks(tags, max_size=500):
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

        if not self.cleanup_temp_directories:
            logger.debug("Skipping cleanup of temporary directories as its disabled")
            return None

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
        """Add missing or mismatched hashes to post resource

        Args:
            post (resources.InternalPost): The post resource to update file hashes for

        Returns:
            resources.InternalPost: The post resource with updated hashes
        """
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
        """Get the MD5 hash for the provided file

        Args:
            file_path (Path): The file to generate a MD5 hash for

        Returns:
            str: The MD5 hash for the file
        """
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
        """Get the SHA1 hash for the provided file

        Args:
            file_path (Path): The file to generate a SHA1 hash for

        Returns:
            str: The SHA1 hash for the file
        """
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
    def split_tag_list(tag_string:str, and_seperator:str="|", or_seperator:str=",") -> list[str|list[str]]:
        """Split a tag string into a list of tags for more complex tag matching`

        Args:
            tag_string (str): The tag string to split into a list
            and_seperator (str, optional): The and seperator for any split strings, creating a sublist. Defaults to "|".
            or_seperator (str, optional): The or seperate to seperate the string with. Defaults to ",".

        Returns:
            list[str|list[str]]: The list of tag strings for more complex tag matching
        """
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
    def divide_chunks(array:list, max_size:int=50) -> Generator[list, None, None]:
        """Divide the provided array into chunks of the provided size through a generator

        Args:
            array (list): The array to divide into chunks
            max_size (int, optional): The max chunk size to split by. Defaults to 50.

        Yields:
            list: The divided chunks of the array
        """
        total_size = len(array)
        for i in range(0, len(array), max_size):
            new_max = i + max_size
            chunk = array[i:new_max]

            chunk_size = len(chunk)
            completion_percent = int((new_max / total_size) * 100)
            if completion_percent > 100:
                completion_percent = 100
            logger.info(f"Creating chunk {i}-{new_max} ({chunk_size} of {total_size} total items) - {completion_percent}% complete")

            yield chunk
    
    def override_plugin_config(self, plugin:object, plugin_override:str=""):
        override_pairs = plugin_override.split(",")
        for pair in override_pairs:
            key, value = pair.split("=")
            setattr(plugin, key, value)

    @staticmethod
    def filter_tags(tags:list[resources.InternalTag]) -> list[resources.InternalTag]:
        """Filter out tags that are in the default/invalid category

        Args:
            tags (list[resources.InternalTag]): The list of tags to filter

        Returns:
            list[resources.InternalTag]: The list of filtered tags
        """
        filtered_tags = []
        for tag in tags:
            if tag in filtered_tags:
                continue
            if tag.category.lower() in [constants.TagCategory._DEFAULT, constants.TagCategory.INVALID]:
                continue
            filtered_tags.append(tag)
        logger.debug(f"Filtered out tags in default category, going from {len(tags)} tags to {len(filtered_tags)} tags")
        return filtered_tags