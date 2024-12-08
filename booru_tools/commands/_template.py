from urllib.parse import urlparse
from pathlib import Path
import json
from loguru import logger

from booru_tools.shared import resources
from booru_tools.plugins import _template
from booru_tools import core
from . import _base

class Command(_base.CommandBase):
    def __init__(self, booru_tools:core.BooruTools):
        self.booru_tools = booru_tools

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
        
        metadata_plugin:_template.MetadataPlugin = self.booru_tools.metadata_loader.init_plugin(domain=domain, category=post_category)
        api_plugin:_template.ApiPlugin = self.booru_tools.api_loader.init_plugin(domain=domain, category=post_category)

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