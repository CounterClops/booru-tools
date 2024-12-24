import click
from loguru import logger
from pathlib import Path

from booru_tools import core
from booru_tools.shared import resources
from booru_tools.plugins import _plugin_template
from booru_tools.tools.gallery_dl import GalleryDl

class ImportPostsCommand():
    def __init__(self, urls:list[str], booru_tools:core.BooruTools, blacklisted_tags:list[str]=[], allowed_blank_pages:int=1, download_page_size:int=100):
        self.urls = urls
        self.booru_tools = booru_tools
        self.blacklisted_tags = blacklisted_tags
        self.allowed_blank_pages = allowed_blank_pages
        self.blank_download_page_count = 0
        self.download_page_size = download_page_size

        self.all_tags:list[resources.InternalTag] = []

    def run(self):
        for url in self.urls:
            try:
                self._import_posts_from_url(url)
            except Exception as e:
                logger.error(f"url import failed with {e}")
        
        self.booru_tools.update_tags(tags=self.all_tags)
        self.booru_tools.cleanup_process_directories()

    def _import_posts_from_url(self, url:str):
        self.gallery_dl = GalleryDl(
            tmp_path=self.booru_tools.tmp_directory,
            urls=[url]
        )

        metadata_downloader = self.gallery_dl.create_bulk_downloader(
            only_metadata=True,
            download_count=self.download_page_size
        )
        
        for download_folder in metadata_downloader:
            posts = self._ingest_folder(folder=download_folder)
            post_count = len(posts)

            self.booru_tools.update_posts(posts=posts)
            self.booru_tools.delete_directory(directory=download_folder)
            if self._check_download_limit_reached(post_count=post_count):
                break
    
    def _ingest_folder(self, folder:Path) -> list[resources.InternalPost]:
        metadata_list = self.booru_tools.import_metadata_files(download_directory=folder)
        logger.debug(f"Reviewing the metadata of {len(metadata_list)} files")

        posts_to_download:list[resources.InternalPost] = []
        all_posts:list[resources.InternalPost] = []

        for metadata in metadata_list:
            post:resources.InternalPost = self.booru_tools.create_post_from_metadata(metadata=metadata, download_link="")
            
            if post.contains_any_tags(tags=self.blacklisted_tags):
                logger.info(f"Skipping '{post.id}' as it contains blacklisted tags from {self.blacklisted_tags}")
                continue
            all_posts.append(post)

            existing_post = self.booru_tools.destination_plugin.find_exact_post(post=post)
            if not existing_post:
                logger.info(f"Queuing up '{post.post_url}' for download")
                posts_to_download.append(post)
            else:
                post:resources.InternalPost = existing_post.create_merged_copy(update_object=post)
                all_posts.append(post)

            # Process tag category data
            for tag in post.tags:
                if tag in self.all_tags:
                    continue
                self.all_tags.append(tag)

        if posts_to_download:
            downloaded_posts = self._download_posts(posts_to_download=posts_to_download, folder=folder)
            all_posts.extend(downloaded_posts)
            self.blank_download_page_count = 0
        else:
            logger.info("No new posts to download")
            self.blank_download_page_count += 1
        
        return all_posts

    def _download_posts(self, posts_to_download:list[resources.InternalPost], folder:Path) -> list[resources.InternalPost]:
        logger.info(f"Downloading {len(posts_to_download)} posts")
        post_urls = [post.post_url for post in posts_to_download]
        self.gallery_dl.download_urls(urls=post_urls, download_folder=folder)

        downloaded_posts:list[resources.InternalPost] = []
        for post in posts_to_download:
            post.local_file = self.booru_tools.get_media_file(metadata=post.metadata)
            downloaded_posts.append(post)
        
        return downloaded_posts
    
    def _check_download_limit_reached(self, post_count:int=0) -> bool:
        if post_count:
            less_posts_than_max = post_count < self.download_page_size
            if less_posts_than_max:
                logger.info(f"Downloaded {post_count} posts, less than the maximum number of posts ({self.download_page_size}), stopping")
                return True
        
        page_count_past_limit = self.blank_download_page_count >= self.allowed_blank_pages
        download_page_limit_disable = self.blank_download_page_count == 0
        if page_count_past_limit and not download_page_limit_disable:
            logger.info(f"Reached the maximum number of blank pages ({self.allowed_blank_pages}), stopping")
            return True
        return False

@click.command()
@click.option('--url', multiple=True, help='URL to import from')
@click.option('--import-site', multiple=True, help='The site name or domain to import from')
@click.option('--urls-file', multiple=True, type=Path, help='A file containing URLs to import')
@click.option('--destination', default="szurubooru", help='Where to send the new posts to')
@click.option('--cookies', type=Path, help='The cookies to use for this download')
@click.option('--blacklisted-tags', type=str, default="", help="A comma seperated list of tags to blacklist")
@click.option('--match-source/--ignore-source', default=True, help="Whether post source should be used when importing")
@click.option('--allowed-blank-pages', type=int, default=1, help="Number of pages to download post pages before stopping")
@click.option('--plugin-override', type=str, help="Provide plugin override values")
@click.option('--download-page-size', type=int, default=100, help="The number of posts to download per page")
def cli(destination:str, url:list[str]=[], import_site:str="", urls_file:Path=None, cookies:Path=None, blacklisted_tags:str="", allowed_blank_pages:int=1, match_source:bool=True, plugin_override:str="", download_page_size:int=100):
    booru_config = {
        "destination": destination
    }
    
    booru_tools = core.BooruTools(
        config=booru_config
    )

    if plugin_override:
        override_pairs = plugin_override.split(",")
        for pair in override_pairs:
            key, value = pair.split("=")
            setattr(booru_tools.destination_plugin, key, value)
    
    if import_site:
        for site_name in import_site:
            site_plugin = booru_tools.metadata_loader.load_matching_plugin(name=site_name, domain=site_name, category=site_name)
            site_url = site_plugin.DEFAULT_POST_SEARCH_URL
            if site_url:
                url.append(site_url)

    if urls_file:
        with open(urls_file, "r") as file:
            lines = file.readlines()
            for line in lines:
                url.append(line.strip())
    
    if destination and not booru_tools.destination_plugin.URL_BASE:
        url_base:str = click.prompt("The provided plugin has no 'url_base', please provide the url start like 'https://danbooru.donmai.us'", type=str)
        url_base = url_base.rstrip("/")
        booru_tools.destination_plugin.URL_BASE = url_base

    blacklisted_tags = blacklisted_tags.split(",")

    command = ImportPostsCommand(
        urls=url,
        booru_tools=booru_tools,
        blacklisted_tags=blacklisted_tags,
        allowed_blank_pages=allowed_blank_pages,
        download_page_size=download_page_size
    )

    command.run()