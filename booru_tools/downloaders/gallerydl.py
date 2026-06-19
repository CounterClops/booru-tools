from typing import Generator
from loguru import logger
from pathlib import Path
import subprocess
import time

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
        self.no_download:list[str] = config_manager["downloaders"]["gallery_dl"]["no_download"]
        self.retry_attempts:int = config_manager["downloaders"]["gallery_dl"]["retry_attempts"]
        self.retry_wait_seconds:int = config_manager["downloaders"]["gallery_dl"]["retry_wait_seconds"]
        self._last_exit_code:int = 0

        if cookies_file:
            logger.debug(f"Using cookies file '{cookies_file}'")
            self.extra_params.extend([
                "--cookies",
                f"{cookies_file}"
            ])
    
    def add_extractor_to_url(self, url:str) -> str:
        """Add the explicit extractor to the url if it's not already present

        Args:
            url (str): The url to prepend the extractor to

        Returns:
            str: The url with the extractor prepended
        """
        if self.extractor and not url.startswith(self.extractor):
            url = f"{self.extractor}:{url}"
        return url

    def call_gallerydl(self, params:list = []) -> int:
        """Call gallery-dl with the given parameters

        Args:
            params (list, optional): The list of params to provide gallery-dl. Defaults to [].

        Returns:
            int: The exit code from the gallery-dl process
        """
        command = [
            "gallery-dl",
            *self.extra_params,
            *params
        ]

        result = subprocess.run(command)
        self._last_exit_code = result.returncode
        if result.returncode != 0:
            logger.warning(f"gallery-dl exited with code {result.returncode}")
        return result.returncode
    
    def download_info(self, urls:list[str], download_directory:Path) -> list[_base.DownloadItem]:
        """Download the metadata for the given urls, without downloading the media files

        Args:
            urls (list[str]): The urls to download metadata for
            download_directory (Path): The directory to download the metadata to

        Returns:
            list[_base.DownloadItem]: The list of DownloadItems created from the downloaded metadata
        """
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

        if not items:
            logger.warning(f"No metadata files found after gallery-dl run in '{download_directory}'")
        else:
            logger.debug(f"Found {len(items)} metadata files in '{download_directory}'")

        return items

    def download_pending_items(self, job:_base.DownloadJob) -> _base.DownloadJob:
        """Download the media files for the given job, that have been marked as desired

        Args:
            job (_base.DownloadJob): The job to download media files for

        Returns:
            _base.DownloadJob: The job with the media files downloaded
        """
        urls = []

        for item in job.download_items:
            if item.resource.post_url:
                item.download_url = item.resource.post_url
            else:
                logger.warning(f"Resource {item.resource} does not have a post_url, using {item._download_override} instead")
                item.download_url = item._download_override
        
        if self.no_download:
            logger.debug("No download flag is set, skipping download")
            return job
        
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
            
            job._downloaded_links.append(item.download_url)

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
        """Create a download job from the given parameters

        Args:
            params (list): The parameters to pass to gallery-dl

        Returns:
            _base.DownloadJob: The created download job
        """
        temp_folder = self.create_temp_folder()
        download_items = self.download_info(params, temp_folder)
        
        job = _base.DownloadJob(
            download_folder = temp_folder,
            download_items=download_items,
            _download_manager = self
        )

        return job

    def download(self, url:str, skip_every_second_page:bool=False) -> Generator[_base.DownloadJob, None, None]:
        """Download the media files from the given url using gallery-dl through a generator function

        Args:
            url (str): The url to download media files from
            skip_every_second_page (bool, optional): Whether each second page should be skipped, can be useful if the download/uploads are going to the same site. Defaults to False.

        Yields:
            Generator[_base.DownloadJob, None, None]: The download job for the given url
        """
        if skip_every_second_page:
            offset_increment = self.page_size
        else:
            offset_increment = 0

        min_range = 0
        max_range = self.page_size

        self._downloaded_links:list[str] = []
        self._sequential_blank_pages = 0

        continue_download = True

        while continue_download:
            params = []
            
            if self.page_size != 0:
                range = f"{min_range}-{max_range}"
                logger.info(f"Downloading range {range} from {url}")
                params.append(f"--range={range}")
            else:
                logger.info(f"Downloading all posts from {url}")
            params.append(self.add_extractor_to_url(url))

            attempt = 0
            while True:
                attempt += 1
                self._last_exit_code = 0
                job = self.create_download_job(params)
                if self._last_exit_code == 0:
                    break
                if attempt < self.retry_attempts:
                    logger.warning(
                        f"gallery-dl failed (exit {self._last_exit_code}) for '{url}', "
                        f"retrying in {self.retry_wait_seconds}s "
                        f"(attempt {attempt}/{self.retry_attempts})"
                    )
                    time.sleep(self.retry_wait_seconds)
                else:
                    logger.error(
                        f"gallery-dl failed (exit {self._last_exit_code}) for '{url}' after "
                        f"{attempt} {'attempt' if attempt == 1 else 'attempts'}, proceeding with empty page"
                    )
                    break

            min_range = max_range + 1 + offset_increment
            max_range += self.page_size + offset_increment
            
            yield job
            continue_download = self._check_continue_download(job)
            self._downloaded_links.extend(job._downloaded_links)
        
        self._downloaded_links = []
        return
    
    def _check_continue_download(self, job:_base.DownloadJob) -> bool:
        """Check if the download should continue based on the given job

        Args:
            job (_base.DownloadJob): The job to check if the download should continue

        Returns:
            bool: Whether the download should continue
        """
        items_pending_download = job.items_pending_download()

        new_items = [
            item for item in job.download_items
            if item.download_url not in self._downloaded_links
        ]

        if self.page_size == 0:
            logger.debug(f"Page size is set 0, so all posts should have been downloaded in prior request")
            return False

        new_items_found = bool(new_items)
        if self.allowed_blank_pages == 0 or self.no_download:
            logger.debug(f"Download check disabled, new items found equal {new_items_found}")
            return new_items_found
        
        if not new_items_found:
            logger.info(f"No new items found, stopping download for this URL")
            return False
        
        is_any_pending_downloads = bool(items_pending_download)
        if not is_any_pending_downloads:
            self._sequential_blank_pages += 1
            logger.info(f"All posts on this page already exist in destination (blank page {self._sequential_blank_pages}/{self.allowed_blank_pages})")

        is_under_allowed_pages = self._sequential_blank_pages < self.allowed_blank_pages
        if is_under_allowed_pages:
            continue_download = True
        else:
            logger.info(f"Reached the blank page limit of {self.allowed_blank_pages}, stopping download for this URL")
            continue_download = False
            
        return continue_download