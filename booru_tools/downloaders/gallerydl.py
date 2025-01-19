from typing import Generator
from loguru import logger
from pathlib import Path
import subprocess

from booru_tools.downloaders import _base
from booru_tools.shared import constants, config

class GalleryDlManager(_base.DownloadManager):
    def __init__(self, extractor:str=None, page_size:int=50, extra_params:list=[]):
        logger.debug(f"Loading {self.__class__.__name__}")
        self.extractor:str = extractor
        self.page_size:int = page_size
        self.extra_params:list = extra_params

        config_manager = config.ConfigManager()
        cookies_file = config_manager['networking']['cookies_file']
        if cookies_file:
            logger.debug(f"Using cookies file '{cookies_file}'")
            self.extra_params.extend([
                "--cookies",
                f"{cookies_file}"
            ])
    
    def add_extractor_to_url(self, url:str) -> str:
        if self.extractor and not url.startswith(self.extractor):
            url = f"{self.extractor}:{url}"
        return url

    def call_gallerydl(self, params:list = []) -> None:
        command = [
            "gallery-dl",
            *self.extra_params,
            *params
        ]

        subprocess.run(command)
        return None
    
    def download_info(self, urls:list[str], download_directory:Path) -> list[_base.DownloadItem]:
        params = [
            "--write-metadata", 
            "--no-download",
            f"-D={download_directory}",
            *urls
        ]

        self.call_gallerydl(params)

        items:list[_base.DownloadItem] = []

        for json_file in download_directory.rglob(f"*.json"):
            item = _base.DownloadItem(
                metadata_file = json_file.absolute()
            )
            items.append(item)
        
        return items

    def download_pending_items(self, job:_base.DownloadJob) -> _base.DownloadJob:
        urls = []
        
        for item in job.download_items:
            if not item.media_download_desired:
                continue

            if item.ignore:
                continue

            if item.resource.post_url:
                download_url = item.resource.post_url
            else:
                logger.warning(f"Resource {item.resource} does not have a post_url, using {item._download_override} instead")
                download_url = item._download_override
            
            if download_url:
                download_url = self.add_extractor_to_url(download_url)
                urls.append(download_url)

        if not urls:
            logger.debug("No media files to download")
            return job
        
        params = [
            *self.extra_params,
            f"-D={job.download_folder}",
            *urls
        ]
        self.call_gallerydl(params)

        for item in job.download_items:
            if not item.media_download_desired:
                continue

            downloaded_file = item.metadata_file.parent / item.metadata_file.stem
            
            if not downloaded_file.exists():
                continue

            logger.debug(f"Found '{downloaded_file}' media file")
            item.media_file = downloaded_file
            item.resource.local_file = downloaded_file
                
        return job

    def create_download_job(self, params:list) -> _base.DownloadJob:
        temp_folder = self.create_temp_folder()
        download_items = self.download_info(params, temp_folder)
        
        job = _base.DownloadJob(
            download_folder = temp_folder,
            download_items=download_items,
            _download_manager = self
        )

        return job

    def download(self, url:str) -> Generator[_base.DownloadJob, None, None]:
        min_range = 0
        max_range = self.page_size

        downloaded_item_count = self.page_size
        
        while downloaded_item_count:
            range = f"{min_range}-{max_range}"

            params = [
                f"--range={range}",
                self.add_extractor_to_url(url)
            ]

            job = self.create_download_job(params)
            downloaded_item_count = job.all_item_count

            min_range = max_range + 1
            max_range += self.page_size
            
            yield job
        
        return