import yt_dlp
from pathlib import Path
from loguru import logger
from typing import Generator
from booru_tools.downloaders import _base

# https://pypi.org/project/yt-dlp/
# https://github.com/yt-dlp/FFmpeg-Builds
# https://github.com/yt-dlp/yt-dlp?tab=readme-ov-file#embedding-yt-dlp

class YtDlpManager(_base.DownloaderBase):
    pass