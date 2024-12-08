from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
import json, shutil, functools

from booru_tools import plugin_loader
from booru_tools.plugins import _template
from booru_tools.shared import errors, resources
from booru_tools.tools.gallery_dl import GalleryDl

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="plugins"):
        program_path = Path(__file__).parent
        self.booru_plugin_directory = program_path / Path(booru_plugin_directory)
        self.load_plugins()

        self.config = {
            "destination": "szurubooru"
        }

    def load_plugins(self) -> None:
        """Loads the plugins for this instances set of loaders
        """
        self.metadata_loader = plugin_loader.PluginLoader(
            plugin_class=_template.MetadataPlugin
        )

        self.metadata_loader.load_plugins_from_directory(directory=self.booru_plugin_directory)

        self.api_loader = plugin_loader.PluginLoader(
            plugin_class=_template.ApiPlugin
        )

        self.api_loader.load_plugins_from_directory(directory=self.booru_plugin_directory)
    
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
        
        metadata_plugin:_template.MetadataPlugin = self.metadata_loader.init_plugin(domain=domain, category=post_category)
        api_plugin:_template.ApiPlugin = self.api_loader.init_plugin(domain=domain, category=post_category)

        post_data = {
            "id": metadata_plugin.get_id(metadata=metadata),
            "category": post_category,
            "sources": metadata_plugin.get_sources(metadata=metadata),
            "description": metadata_plugin.get_description(metadata=metadata),
            "tags": metadata_plugin.get_tags(metadata=metadata),
            "created_at": metadata_plugin.get_created_at(metadata=metadata),
            "updated_at": metadata_plugin.get_updated_at(metadata=metadata),
            "relations": metadata_plugin.get_relations(metadata=metadata),
            "safety": metadata_plugin.get_safety(metadata=metadata),
            "md5": metadata_plugin.get_md5(metadata=metadata),
            "post_url": metadata_plugin.get_post_url(metadata=metadata),
            "pools": metadata_plugin.get_pools(metadata=metadata),
            "local_file": self.get_media_file(metadata=metadata),
            "plugins": resources.InternalPlugins(
                api=api_plugin,
                meta=metadata_plugin
            ),
            "metadata": metadata
        }
        
        post = resources.InternalPost(
            **post_data
        )
        
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

    def get_media_file(self, metadata:resources.Metadata) -> Path | None:
        media_file = metadata.file.parent / metadata.file.stem
        if media_file.exists():
            logger.debug(f"Found '{media_file}' media file")
            return media_file
        return None

    def sync(self, urls:dict=[], input_file:str=""):
        gallery_dl = GalleryDl(
            tmp_path=Path("tmp"),
            urls=urls,
            input_file=input_file
        )

        metadata_downloader = gallery_dl.create_bulk_downloader(
            only_metadata=True
        )

        # pools:dict[int, resources.InternalPool] = {}
        tags:list[resources.InternalTag] = []

        destination = self.config["destination"]
        destination_api_plugin:_template.ApiPlugin = self.api_loader.init_plugin(domain=destination, category=destination)

        for download_folder in metadata_downloader:
            metadata_list = self.import_metadata_files(download_directory=download_folder)
            logger.debug(f"Reviewing the metadata of {len(metadata_list)} files")

            posts_to_download:list[resources.InternalPost] = []
            posts:list[resources.InternalPost] = []

            for metadata in metadata_list:
                post:resources.InternalPost = self.create_post_from_metadata(metadata=metadata, download_link="")
                posts.append(post)

                existing_post = destination_api_plugin.find_exact_post(post=post)

                if not existing_post:
                    logger.info(f"Queuing up '{post.post_url}' for download")
                    posts_to_download.append(post)
                

                # # Process pool data
                # for pool in post.pools:
                #     if pool.id in pools:
                #         pools[pool.id].posts.append(post)
                #     else:
                #         pools[pool.id] = pool

                # Process tag category data
                for tag in post.tags:
                    if tag in tags:
                        continue
                    tags.append(tag)

            if posts_to_download:
                logger.info(f"Downloading {len(posts_to_download)} posts")
                post_urls = [post.post_url for post in posts_to_download]
                gallery_dl.download_urls(urls=post_urls, download_folder=download_folder)
                for post in posts_to_download:
                    post.local_file = self.get_media_file(metadata=post.metadata)

            self.upload_posts(posts=posts)
            # try:
            #     self.upload_posts(posts=posts_to_download)
            # except Exception as e:
            #     logger.critical(f"Post upload failed due to {e}")
            
            logger.debug(f"Deleting '{download_folder}' folder")
            shutil.rmtree(download_folder)

        self.update_tags(tags=tags)
        # self.update_pools(pools=pools)

    def check_post_exists(self, post:resources.InternalPost) -> resources.InternalPost:
        """Check if the provided post (see metadata) already exists on the destination booru

        Args:
            metadata (dict): The post metadata

        Returns:
            int: The post ID of the destination post
        """
        post = None
        
        destination = self.config["destination"]
        api_plugin:_template.ApiPlugin = self.api_loader.init_plugin(domain=destination, category=destination)

        try:
            if post.post_url:
                logger.debug(f"Found post_url in metadata of value '{post.post_url}'")
                sources = [post.post_url]
                post = api_plugin.check_sources_post_exists(sources=sources)
        except KeyError:
            logger.debug(f"No post_url attribute to check on {post.id}")

        if post:
            logger.debug(f"Existing post found on '{destination}'")

        return post
    
    def upload_posts(self, posts:list[resources.InternalPost]):
        for post in posts:
            if not post.local_file:
                logger.debug(f"No file to upload for '{post.id}'")
            else:
                logger.debug(f"Uploading {post.local_file.name} for '{post.id}'")

            if post.post_url:
                post.sources.append(post.post_url)

            destination:str = self.config["destination"]
            api_plugin:_template.ApiPlugin = self.api_loader.init_plugin(domain=destination, category=destination)
            api_plugin.push_post(
                post=post
            )

    def update_tags(self, tags:list[resources.InternalTag]):
        destination = self.config["destination"]
        api_plugin:_template.ApiPlugin = self.api_loader.init_plugin(domain=destination, category=destination)

        logger.info(f"Updating {len(tags)} tags")

        # for tag in self.implicate_tags(tags):
        for tag in tags:
            logger.debug(f"Updating tag '{tag}' to category '{tag.category}'")
            try:
                api_plugin.push_tag(tag=tag)
            except Exception as e:
                logger.warning(f"Error updating the tag '{tag}' due to {e}")