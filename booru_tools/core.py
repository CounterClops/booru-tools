from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
from collections import defaultdict
import json
import shutil
import hashlib
import asyncio
import aiohttp
import signal

from booru_tools.loaders import plugin_loader
from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, resources, constants

class GracefulExit(SystemExit):
    code = 1

class SessionManager:
    def __init__(self):
        self.session = None
        self.limit_per_host = 25
        self.default_headers = {
            "User-Agent": "BooruTools/1.0"
        }

    def start(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            limit_per_host=self.limit_per_host
        )
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.default_headers,
                skip_auto_headers=self.default_headers.keys(),
                connector=connector
            )
        return self.session

    async def close(self):
        logger.debug("Closing aiohttp session")
        await self.session.close()

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="", config:dict=defaultdict(dict), tmp_path:str="tmp"):
        if not booru_plugin_directory:
            program_path = constants.ROOT_FOLDER
            self.booru_plugin_directory = program_path / Path("plugins")
        else:
            self.booru_plugin_directory = Path(booru_plugin_directory)
        
        self.tmp_directory = constants.TEMP_FOLDER
        self.config = config
        self.session_manager = SessionManager()

        signal.signal(signal.SIGINT, self.raise_graceful_exit)
        signal.signal(signal.SIGTERM, self.raise_graceful_exit)

        try:
            self.session_manager.start()
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

        if self.config["destination"]:
            self.destination_plugin:_plugin_template.ApiPlugin = self.api_loader.load_matching_plugin(domain=self.config["destination"], category=self.config["destination"])
    
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

    def create_post_from_metadata(self, metadata:resources.Metadata, download_link:str) -> resources.InternalPost:
        try:
            file_url:str = metadata["file"]["url"]
            domain:str = urlparse(file_url).hostname
        except KeyError:
            domain:str = urlparse(download_link).hostname

        try:
            post_category:str = metadata["category"]
        except KeyError:
            post_category:str = ""
        
        metadata_plugin:_plugin_template.MetadataPlugin = self.metadata_loader.load_matching_plugin(domain=domain, category=post_category)
        api_plugin:_plugin_template.ApiPlugin = self.api_loader.load_matching_plugin(domain=domain, category=post_category)
        validator_plugins:list[_plugin_template.ValidationPlugin] = self.validation_loader.load_all_plugins()

        plugins = resources.InternalPlugins(
            api=api_plugin,
            meta=metadata_plugin,
            validators=validator_plugins
        )
        
        post = metadata_plugin.from_metadata_file(metadata_file=metadata.file, plugins=plugins)
        
        return post

    def import_metadata_files(self, download_directory:Path, metadata_file_extension:str="json") -> list[resources.Metadata]:
        """Imports the metadata from the provided metadata files

        Args:
            download_directory (Path): The path the metadata files are downloaded to
            metadata_file_extension (str, optional): The file extension of the metadata files. Defaults to "json".

        Returns:
            metadata_list (list[resources.Metadata]): The list of metadata that was pulled from each file
        """
        metadata_list:list[resources.Metadata] = []

        for json_file in download_directory.rglob(f"*.{metadata_file_extension}"):
            with open(json_file) as file:
                metadata = resources.Metadata(
                    data=json.load(file),
                    file=json_file.absolute()
                )
                metadata_list.append(metadata)

        return metadata_list
    
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
    
    def get_media_file(self, metadata:resources.Metadata) -> Path | None:
        media_file = metadata.file.parent / metadata.file.stem
        if media_file.exists():
            logger.debug(f"Found '{media_file}' media file")
            return media_file
        return None
    
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