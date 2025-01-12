from pathlib import Path
from typing import Generator

class DownloaderBase:
    def __init__(self, tmp_path: Path = Path("tmp")):
        self.tmp_path = tmp_path

    def download(self, url: str, only_metadata: bool = False) -> Generator[Path, None, None]:
        """Download content from the given URL.

        Args:
            url (str): The URL to download content from.
            only_metadata (bool): Whether to download only metadata.

        Yields:
            Path: The path to the downloaded content.
        """
        raise NotImplementedError("Subclasses must implement this method")