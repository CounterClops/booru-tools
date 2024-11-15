import plugin_loader
from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
import json
import shutil

from boorus.shared import errors
from boorus.shared.meta import CommonBooru
from boorus.shared.api_client import ApiClient
from tools.gallery_dl import GalleryDl

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="boorus"):
        program_path = Path(__file__).parent
        self.booru_plugin_directory = program_path / Path(booru_plugin_directory)

        self.metadata_loader = plugin_loader.PluginLoader(
            plugin_class=CommonBooru
        )

        self.api_loader = plugin_loader.PluginLoader(
            plugin_class=ApiClient
        )

        self.load_plugins()

        self.plugin_configs = {
            "szurubooru" : {
                "url_base": "https://szurubooru.equus.soy",
                "username": "e621-sync",
                "password": "7dc645f5-b525-43b0-a27b-3362d5e8bb2f"
            }
        }

        self.config = {
            "destination": "szurubooru"
        }

    def load_plugins(self):
        """Loads the plugins for this instances set of loaders
        """
        self.metadata_loader.load_plugins_from_directory(directory=self.booru_plugin_directory)
        self.api_loader.load_plugins_from_directory(directory=self.booru_plugin_directory)

    def find_plugin(self, plugins:list, domain:str="", category:str="") -> plugin_loader.Plugin:
        """Find plugin that matches the desired service, it will return a plugin if any single condition matches

        Args:
            plugins (list): The list of plugins to search
            domain (list, optional): The domain of the service to match with the plugin. Defaults to [].
            category (list, optional): The category of the service to match with the plugin. Defaults to [].

        Raises:
            plugin_loader.NoPluginFound: When a plugin that matches the provided criteria isn't found in the provided list of plugins

        Returns:
            _type_: The first plugin to match the desired conditions
        """
        logger.debug(f"Searching {len(plugins)} plugins for domain={domain}, category={category}")

        for plugin in plugins:
            try:
                plugin_domains = plugin.obj._DOMAINS
                logger.debug(f"Domain search: '{domain}' in '{plugin_domains}'")
                plugin_domain_matches = any(plugin_domain in domain for plugin_domain in plugin_domains)
                if plugin_domain_matches:
                    logger.debug(f"Found '{plugin}' with domain match")
                    return plugin
            except (TypeError, AttributeError):
                pass
            
            try:
                plugin_category = plugin.obj._CATEGORY
                logger.debug(f"Category search: '{category}' in '{plugin_category}'")
                plugin_category_matches = any(category in plugin_category for plugin_category in plugin_category)
                if plugin_category_matches:
                    logger.debug(f"Found '{plugin}' with category match")
                    return plugin
            except (TypeError, AttributeError):
                pass
            
        raise plugin_loader.NoPluginFound

    def find_metadata_plugin(self, domain:str="", category:str="") -> plugin_loader.Plugin:
        """Find metadata plugin that matches the desired domain or category

        Args:
            domain (str, optional): The domain to search for in the plugin. Defaults to "".
            category (str, optional): The category to search for in the plugin. Defaults to "".

        Returns:
            plugin_loader.Plugin: The first plugin that matches the search
        """
        logger.debug(f"Starting metadata plugin search for domain={domain}, category={category}")

        plugin = self.find_plugin(
            plugins=self.metadata_loader.plugins,
            domain=domain,
            category=category
        )

        try:
            plugin_name = plugin.obj._NAME
            logger.debug(f"Checking for plugin config for '{plugin_name}'")
            config = self.plugin_configs[plugin_name]
            logger.debug(f"Found plugin config for '{plugin_name}'")
        except (AttributeError, KeyError):
            logger.debug(f"No plugin config found for '{plugin_name}'")
            config = {}

        return plugin(config=config)

    def find_api_plugin(self, domain:str="", category:str="") -> plugin_loader.Plugin:
        """Find api plugin that matches the desired domain or category

        Args:
            domain (str, optional): The domain to search for in the plugin. Defaults to "".
            category (str, optional): The category to search for in the plugin. Defaults to "".

        Returns:
            plugin_loader.Plugin: The first plugin that matches the search
        """
        logger.debug(f"Starting api plugin search for domain={domain}, category={category}")

        plugin = self.find_plugin(
            plugins=self.api_loader.plugins,
            domain=domain,
            category=category
        )

        try:
            plugin_name = plugin.obj._NAME
            logger.debug(f"Checking for plugin config for '{plugin_name}'")
            config = self.plugin_configs[plugin_name]
            logger.debug(f"Found plugin config for '{plugin_name}'")
        except (AttributeError, KeyError):
            logger.debug(f"No plugin config found for '{plugin_name}'")
            config = {}

        return plugin(config=config)

    def adjust_metadata(self, metadata:dict) -> dict:
        """Parse the provided metadata and update using the appropriate metadata plugin

        Args:
            metadata (dict): The input metadata object

        Returns:
            metadata (dict): The updated metadata object
        """
        domain = urlparse(metadata.get("file_url", "")).hostname
        category = metadata["category"]
        metadata_plugin = self.find_metadata_plugin(domain=domain, category=category)

        try:
            metadata = metadata_plugin.add_tag_category_map(metadata)
        except AttributeError:
            logger.debug(f"No 'add_tag_category_map' function in {metadata_plugin}")

        try:
            metadata = metadata_plugin.add_post_url(metadata)
        except AttributeError:
            logger.debug(f"No 'add_post_url' function in {metadata_plugin}")

        try:
            metadata = metadata_plugin.update_sources(metadata=metadata)
            post_url = metadata["post_url"]
            metadata["sources"].append(post_url)
            logger.debug(f"Updates sources on {metadata['id']} to {metadata["sources"]}")
        except AttributeError:
            logger.debug(f"No 'update_sources' function in {metadata_plugin}")

        return metadata

    def import_metadata(self, download_directory:Path, metadata_file_extension:str="json") -> list:
        """Imports the metadata from the provided metadata files

        Args:
            download_directory (Path): The path the metadata files are downloaded to
            metadata_file_extension (str, optional): The file extension of the metadata files. Defaults to "json".

        Returns:
            metadata_list (list): The list of metadata that was pulled from each file
        """
        metadata_list = []
        for json_file in download_directory.rglob(f"*.{metadata_file_extension}"):
            with open(json_file) as file:
                metadata = json.load(file)
                metadata["metadata_absolute_path"] = json_file.absolute()
                metadata_list.append(metadata)

        return metadata_list

    def get_media_file(self, metadata:dict) -> Path:
        metadata_file = Path(metadata["metadata_absolute_path"])

        media_file = metadata_file.parent / metadata_file.stem
        if media_file.exists():
            logger.debug(f"Confirmed '{media_file}' file exists, returning")
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

        pools = {}
        tag_categories = {}

        for download_folder in metadata_downloader:
            metadata_list = self.import_metadata(download_directory=download_folder)
            logger.debug(f"Reviewing the metadata of {len(metadata_list)} files")

            posts_to_download = []

            for metadata in metadata_list:
                metadata = self.adjust_metadata(metadata=metadata) # Update sources if required
                destination_post_id = self.check_post_exists(metadata=metadata)

                if not destination_post_id:
                    logger.info(f"Queuing up '{metadata["post_url"]}' for download")
                    posts_to_download.append(metadata)
                else:
                    logger.debug(f"Updating post {destination_post_id}")
                    # Update tags on existing posts if required
                    # Update sources on existing posts
                
                # Process pool data
                post_pools = metadata.get("pools", [])
                for pool_id in post_pools:
                    try:
                        pools[pool_id]
                    except KeyError:
                        pools[pool_id] = []
                    pools[pool_id] += [metadata]

                # Process tag category data
                new_tag_categories = metadata.get("tag_category_map", {})
                tag_categories = {**tag_categories, **new_tag_categories}

            if posts_to_download:
                logger.info(f"Downloading {len(posts_to_download)} posts")
                post_urls = [metadata["post_url"] for metadata in posts_to_download]
                gallery_dl.download_urls(urls=post_urls, download_folder=download_folder)

            try:
                self.upload_posts(metadata_list=posts_to_download)
            except Exception as e:
                logger.critical(f"Post upload failed due to {e}")
            
            logger.debug(f"Deleting '{download_folder}' folder")
            shutil.rmtree(download_folder)

        self.update_tag_categories(tag_categories=tag_categories)
        self.update_pools(pools=pools)

    def check_post_exists(self, metadata:dict) -> int:
        """Check if the provided post (see metadata) already exists on the destination booru

        Args:
            metadata (dict): The post metadata

        Returns:
            int: The post ID of the destination post
        """
        existing_post_id = None
        domain = urlparse(metadata.get("file_url", "")).hostname
        category = metadata["category"]

        metadata_plugin = self.find_metadata_plugin(domain=domain, category=category)

        destination = self.config["destination"]
        api_plugin = self.find_api_plugin(domain=destination, category=destination)

        try:
            md5 = metadata_plugin.get_md5(metadata=metadata)
            logger.debug(f"Found md5 in metadata of value '{md5}'")
            existing_post_id = api_plugin.check_md5_post_exists(md5_hash=md5)
        except errors.MissingMd5:
            logger.debug(f"No md5 attribute to check on {metadata.get('id', 'NA')}")

        if not existing_post_id:
            try:
                post_url = metadata["post_url"]
                logger.debug(f"Found post_url in metadata of value '{post_url}'")
                sources = [post_url]
                existing_post_id = api_plugin.check_sources_post_exists(sources=sources)
            except KeyError:
                logger.debug(f"No post_url attribute to check on {metadata.get('id', 'NA')}")

        if existing_post_id:
            logger.debug(f"Existing post found on '{destination}'")

        return existing_post_id
    
    def upload_posts(self, metadata_list:list):
        for metadata in metadata_list:
            media_file = self.get_media_file(metadata=metadata)

            if not media_file:
                post_id = metadata.get("id", "NA")
                logger.debug(f"No file to upload for '{post_id}'")
                continue
            
            domain = urlparse(metadata.get("file_url", "")).hostname
            category = metadata["category"]
            metadata_plugin = self.find_metadata_plugin(domain=domain, category=category)
            post = metadata_plugin.create_standard_post(
                metadata=metadata
            )

            logger.info(f"Starting upload of {media_file.name}")
            destination = self.config["destination"]
            api_plugin = self.find_api_plugin(domain=destination, category=destination)
            api_plugin.push_post(
                file=media_file, 
                post=post
            )

    def update_tag_categories(self, tag_categories:dict):
        destination = self.config["destination"]
        api_plugin = self.find_api_plugin(domain=destination, category=destination)

        tags = tag_categories.keys()
        logger.info(f"Updating {len(tags)} tags")

        for tag, category in tag_categories.items():
            logger.debug(f"Updating tag '{tag}' to category '{category}'")
            try:
                api_plugin.push_tag(tag=tag, tag_category=category)
            except Exception as e:
                logger.warning(f"Error updating the tag '{tag}' due to {e}")

    def update_pools(self, pools:dict):
        destination = self.config["destination"]
        destination_api_plugin = self.find_api_plugin(domain=destination, category=destination)

        for source_pool_id, metadata_list in pools.items():
            metadata = metadata_list[0]

            domain = urlparse(metadata.get("file_url", "")).hostname
            category = metadata["category"]

            api_plugin = self.find_api_plugin(domain=domain, category=category)
            pool = api_plugin.get_pool(id=source_pool_id)
            
            post_ids_ordered = []
            for post_id in pool.posts:
                metadata = next((metadata for metadata in metadata_list if metadata['id'] == post_id), None)

                if not metadata:
                    logger.warning(f"Missing metadata for post ID {post_id} in pool {pool.id}, skipping")
                    continue
                
                destination_post_id = self.check_post_exists(metadata=metadata)
                post_ids_ordered.append(destination_post_id)
            
            pool.posts = post_ids_ordered
            destination_api_plugin.push_pool(pool=pool)