import subprocess
from datetime import datetime
from pathlib import Path
from loguru import logger
from typing import Generator
from booru_tools.downloaders import _base

class GalleryDl(_base.DownloaderBase):
    def __init__(self, tmp_path: Path = Path("tmp"), cookies: str = "", verbose: bool = False, warning: bool = True):
        super().__init__(tmp_path)
        self.basic_params = []
        self.extra_params = []

        if cookies:
            logger.debug("Setting cookies")
            self.basic_params.append(f"--cookies={cookies}")
        if verbose:
            logger.debug("Setting gallery-dl to verbose")
            self.basic_params.append("--verbose")
        else:
            if warning:
                logger.debug("Setting gallery-dl to warning")
                self.basic_params.append("--warning")
            else:
                logger.debug("Setting gallery-dl to quiet")
                self.basic_params.append("--quiet")

    def download(self, url: str, only_metadata: bool = False) -> Generator[Path, None, None]:
        self.extra_params = [url]
        min_range = 0
        max_range = 100

        while True:
            range_str = f"{min_range}-{max_range}"
            params = ["--write-metadata", f"--range={range_str}"]
            if only_metadata:
                params.append("--no-download")

            download_directory = self.call(params=params)
            file_count = self.analyze_files(download_directory)

            if file_count == 0:
                break

            yield download_directory

            min_range = max_range
            max_range += 100

    def call(self, params: list = [], download_folder: str = "") -> Path:
        if download_folder:
            download_directory = download_folder
        else:
            current_time = datetime.now()
            timestamp = str(current_time.timestamp())
            download_directory = self.tmp_path / timestamp

        command = ["gallery-dl", f"-D={download_directory}"]
        command += params
        command += self.basic_params
        command += self.extra_params

        logger.debug(f"Calling {command}")
        subprocess.run(command)
        return download_directory

    def analyze_files(self, path: Path) -> int:
        files = list(path.glob("*.json"))
        file_count = len(files)
        logger.debug(f"Downloaded {file_count} files")
        return file_count
