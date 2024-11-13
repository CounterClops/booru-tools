import subprocess
from datetime import datetime
from pathlib import Path
from loguru import logger

class GalleryDl:
    def __init__(self, tmp_path:Path=Path("tmp"), cookies:str="", urls:dict=[], input_file:str="", verbose:bool=False):
        self.tmp_path = tmp_path
        self.basic_params = []
        self.extra_params = []

        if cookies:
            logger.debug("Setting cookies")
            self.basic_params.append(f"--cookies={cookies}")
        if verbose:
            logger.debug("Setting gallery-dl to verbose")
            self.basic_params.append("-q")
        if urls:
            logger.debug(f"Setting urls to {urls}")
            self.extra_params += urls
        if input_file:
            logger.debug(f"Setting input file to {input_file}")
            self.extra_params.append(f"--input-file={input_file}")


    def call(self, params: list = [], add_extra_params:bool=True, download_folder:str="") -> Path:
        if download_folder:
            download_directory = download_folder
        else:
            current_time = datetime.now()
            timestamp = str(current_time.timestamp())
            download_directory = self.tmp_path / timestamp

        command = [
            "gallery-dl",
            f"-D={download_directory}",
        ]

        command += params
        command += self.basic_params
        
        if add_extra_params:
            command += self.extra_params

        logger.debug(f"Calling {command}")

        subprocess.run(command)
        return download_directory
    
    def download_only_metadata(self, min_range:int=0, max_range:int=100) -> Path:
        range = f"{min_range}-{max_range}"
        params = [
            "--write-metadata", 
            "--no-download", 
            f"--range={range}"
        ]

        download_directory = self.call(params=params)
        return download_directory

    def download_files(self, min_range:int=0, max_range:int=100) -> Path:
        range = f"{min_range}-{max_range}"
        params = [
            "--write-metadata",
            f"--range {range}"
        ]

        download_directory = self.call(params=params)
        return download_directory

    def download_urls(self, urls:dict, download_folder:Path=None) -> Path:
        params = []
        params += urls
        
        download_directory = self.call(params=params, add_extra_params=False, download_folder=download_folder)
        return download_directory

    def create_bulk_downloader(self, only_metadata:bool=False, download_count:int=100, metadata_extension:str="json") -> "GalleryDl.BulkDownload":
        return self.BulkDownload(
            gallery_dl_instance = self, 
            only_metadata = only_metadata, 
            download_count = download_count, 
            metadata_extension = metadata_extension
        )

    class BulkDownload:
        def __init__(self, gallery_dl_instance:'GalleryDl', only_metadata:bool=True, download_count:int=100, metadata_extension:str="json"):
            self.gallery_dl_instance = gallery_dl_instance
            self.download_count = download_count
            self.metadata_extension = metadata_extension
            self.only_metadata = only_metadata

        def __iter__(self) -> "GalleryDl.BulkDownload":
            self.min_range = 0
            self.max_range = self.download_count
            self.previous_files = []
            self.page = 0
            return self

        def analyze_files(self, path:Path) -> int:
            files = path.glob(f"*.{self.metadata_extension}")
            file_count = len(
                list(files)
            )

            logger.debug(f"Downloaded {file_count} files")
            return file_count

        def __next__(self) -> Path:
            logger.info(f"Downloading {self.min_range}-{self.max_range} with only_metadata={self.only_metadata}")
            if self.only_metadata:
                download_directory = self.gallery_dl_instance.download_only_metadata(
                    min_range=self.min_range,
                    max_range=self.max_range
                )
            else:
                download_directory = self.gallery_dl_instance.download_files(
                    min_range=self.min_range,
                    max_range=self.max_range
                )

            self.min_range = self.max_range
            self.max_range += self.download_count

            file_count = self.analyze_files(path=download_directory)

            if not file_count:
                raise StopIteration

            return download_directory
            