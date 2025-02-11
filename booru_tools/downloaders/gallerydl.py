from typing import Generator
from loguru import logger
from pathlib import Path
import subprocess

from booru_tools.downloaders import _base
from booru_tools.shared import constants, config

class GalleryDlManager(_base.DownloadManager):
    def __init__(self, extractor:str=None, extra_params:list=[]):
        logger.debug(f"Loading {self.__class__.__name__}")
        self.extractor:str = extractor
        
        self.extra_params:list = extra_params
        self._downloaded_links:list[str] = []

        config_manager = config.shared_config_manager
        cookies_file:Path = config_manager['networking']['cookies_file']
        self.page_size:int = config_manager["downloaders"]["gallery_dl"]["page_size"]
        self.allowed_blank_pages:int = config_manager["downloaders"]["gallery_dl"]["allowed_blank_pages"]
        self.ignored_file_extensions:list[str] = config_manager["downloaders"]["gallery_dl"]["ignored_file_extensions"]

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
            if item.resource.post_url:
                item.download_url = item.resource.post_url
            else:
                logger.warning(f"Resource {item.resource} does not have a post_url, using {item._download_override} instead")
                item.download_url = item._download_override
        
        for item in job.items_pending_download():
            file_to_download = item.metadata_file.parent / item.metadata_file.stem
            if file_to_download.suffix in self.ignored_file_extensions:
                logger.debug(f"Skipping download of {file_to_download.name} as it's in the ignored file extensions list")
                item.media_download_desired = False
                continue

            if item.ignore:
                continue
            
            if item.download_url in self._downloaded_links:
                logger.debug(f"Skipping download of {item.download_url} as it's already been downloaded")
                item.media_download_desired = False
                continue
            
            if item.download_url:
                download_url = self.add_extractor_to_url(item.download_url)
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
        self._downloaded_links.extend(urls)

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

        self._downloaded_links:list[str] = []
        self._sequential_blank_pages = 0

        continue_download = True

        while continue_download:
            range = f"{min_range}-{max_range}"
            logger.debug(f"Downloading range {range} from {url}")

            params = [
                f"--range={range}",
                self.add_extractor_to_url(url)
            ]

            job = self.create_download_job(params)

            min_range = max_range + 1
            max_range += self.page_size
            
            yield job
            continue_download = self._check_continue_download(job)
        
        return
    
    def _check_continue_download(self, job:_base.DownloadJob) -> bool:
        items_pending_download = job.items_pending_download()

        new_items = [
            item for item in job.download_items
            if item.download_url not in self._downloaded_links
        ]

        new_items_found = bool(new_items)
        if self.allowed_blank_pages == 0:
            logger.debug(f"Allowed_blank_pages is set to 0, new items found equal {new_items_found}")
            return new_items_found
        
        
        logger.debug(f"Checking if download should continue")
        if not new_items_found:
            return False
        
        is_any_pending_downloads = bool(items_pending_download)
        if not is_any_pending_downloads:
            self._sequential_blank_pages += 1
            logger.debug(f"Incrementing the sequential blank pages count to {self._sequential_blank_pages}")

        is_under_allowed_pages = self._sequential_blank_pages < self.allowed_blank_pages
        if is_under_allowed_pages:
            continue_download = True
        else:
            logger.debug(f"Reached the blank page limit of {self.allowed_blank_pages}, stopping download")
            continue_download = False
            
        return continue_download