from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Generator, Optional, Any
import shutil

from booru_tools.shared import constants, resources

@dataclass(kw_only=True)
class DownloadItem:
    metadata_file:Path = field(compare=True)
    media_file:Path = field(default=None)
    media_download_desired:bool = field(default=False)
    ignore:bool = field(default=False)
    resource:resources.InternalPost = field(default=None)
    _download_override:Any = field(repr=False, default=None)

@dataclass(kw_only=True)
class DownloadJob:
    download_folder:Path = field(compare=True)
    download_items:list[DownloadItem] = field(default_factory=list)
    _download_manager:DownloadManager = field(repr=False, default=None)

    def download_media(self) -> None:
        self._download_manager.download_pending_items(job=self)
        return None
    
    def all_item_count(self, only_download_desired:bool=False) -> int:
        if not only_download_desired:
            return len(self.download_items)
        
        return len(self.items_pending_download())
    
    def items_pending_download(self) -> list[DownloadItem]:
        return [item for item in self.download_items if item.media_download_desired]

    def cleanup_folders(self) -> None:
        if self.download_folder.exists():
            shutil.rmtree(self.download_folder)
        return None

class DownloadManager:
    def create_temp_folder(self) -> Path:
        current_time = datetime.now()
        timestamp = str(current_time.timestamp())
        temp_folder = constants.TEMP_FOLDER / timestamp
        return temp_folder

    def download_info(self, urls:list[str], download_directory:Path) -> list[DownloadItem]:
        raise NotImplementedError

    def download_pending_items(self, job:DownloadJob) -> DownloadJob:
        raise NotImplementedError

    def create_download_job(self, params:list) -> DownloadJob:
        raise NotImplementedError

    def download(self, url:str) -> Generator[DownloadJob, None, None]:
        raise NotImplementedError