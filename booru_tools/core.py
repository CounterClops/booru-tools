from pathlib import Path
from urllib.parse import urlparse
from loguru import logger
from collections import defaultdict
import json
import shutil

from booru_tools.loaders import plugin_loader
from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, resources

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="", config:dict=defaultdict(dict), tmp_path:str="tmp"):
        if not booru_plugin_directory:
            program_path = Path(__file__).parent
            self.booru_plugin_directory = program_path / Path(booru_plugin_directory)
        else:
            self.booru_plugin_directory = Path(booru_plugin_directory)
        
        self.tmp_directory = Path(tmp_path)
        self.config = config
        self.load_plugins()
    
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
            plugin_class=_plugin_template.ApiPlugin
        )
        self.api_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        self.validation_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.ValidationPlugin
        )
        self.validation_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        if self.config["destination"]:
            self.destination_plugin:_plugin_template.ApiPlugin = self.api_loader.load_matching_plugin(domain=self.config["destination"], category=self.config["destination"])
    
    def update_posts(self, posts:list[resources.InternalPost]):
        for post in posts:
            if not post.local_file:
                logger.debug(f"No file to upload for '{post.id}'")
            else:
                logger.debug(f"Uploading {post.local_file.name} for '{post.id}'")

            if post.post_url:
                post.sources.append(post.post_url)

            self.destination_plugin.push_post(
                post=post
            )

    def update_tags(self, tags:list[resources.InternalTag]):
        logger.info(f"Updating {len(tags)} tags")

        # for tag in self.implicate_tags(tags):
        for tag in tags:
            logger.debug(f"Updating tag '{tag}' to category '{tag.category}'")
            try:
                self.destination_plugin.push_tag(tag=tag)
            except Exception as e:
                logger.warning(f"Error updating the tag '{tag}' due to {e}")

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
                meta=metadata_plugin,
                validators=validator_plugins
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