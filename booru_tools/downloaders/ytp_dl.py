import yt_dlp
from pathlib import Path
from loguru import logger
from typing import Generator
from booru_tools.downloaders import _base

# https://pypi.org/project/yt-dlp/
# https://github.com/yt-dlp/FFmpeg-Builds
# https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#embedding-yt-dlp

class YtDlp(_base.DownloaderBase):
    def __init__(self, tmp_path: Path = Path("tmp")):
        super().__init__(tmp_path)
        self.yt_dlp = yt_dlp.YoutubeDL()

    def download(self, url: str, only_metadata: bool = False) -> Generator[Path, None, None]:
        min_range = 0
        max_range = 100

        while True:
            download_directory = self.create_tmp_directory()
            params = {
                "outtmpl": str(download_directory / "%(title)s.%(ext)s"),
                "quiet": True,
                "noplaylist": True,
                "playliststart": min_range + 1,
                "playlistend": max_range,
            }
            if only_metadata:
                params["skip_download"] = True

            self.yt_dlp.params.update(params)
            self.yt_dlp.download([url])

            file_count = self.analyze_files(download_directory)

            if file_count == 0:
                break

            yield download_directory

            min_range = max_range
            max_range += 100

    def analyze_files(self, path: Path) -> int:
        files = list(path.glob("*"))
        file_count = len(files)
        logger.debug(f"Downloaded {file_count} files")
        return file_count