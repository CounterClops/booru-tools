import click
from loguru import logger
from pathlib import Path
import asyncio

from booru_tools import core
from booru_tools.shared import resources
from booru_tools.plugins import _plugin_template
from booru_tools.tools.gallery_dl import GalleryDl


class ImportPostsCommand():
    def __init__(self):
        self.blank_download_page_count = 0
        self.all_tags:list[resources.InternalTag] = []
    
    async def post_init(self, destination:str, url:list[str]=[], import_site:str="", urls_file:Path=None, cookies:Path=None, blacklisted_tags:str="", required_tags:str="", allowed_blank_pages:int=1, match_source:bool=True, plugin_override:str="", download_page_size:int=100):
        booru_config = {
            "destination": destination
        }
        
        self.booru_tools = core.BooruTools(
            config=booru_config
        )

        if plugin_override:
            override_pairs = plugin_override.split(",")
            for pair in override_pairs:
                key, value = pair.split("=")
                setattr(self.booru_tools.destination_plugin, key, value)
        
        self.urls = url
        if import_site:
            for site_name in import_site:
                site_plugin = self.booru_tools.metadata_loader.load_matching_plugin(name=site_name, domain=site_name, category=site_name)
                site_url = site_plugin.DEFAULT_POST_SEARCH_URL
                if site_url:
                    self.urls.append(site_url)

        if urls_file:
            with open(urls_file, "r") as file:
                lines = file.readlines()
                for line in lines:
                    self.urls.append(line.strip())
        
        if destination and not self.booru_tools.destination_plugin.URL_BASE:
            url_base:str = click.prompt("The provided plugin has no 'url_base', please provide the url start like 'https://danbooru.donmai.us'", type=str)
            url_base = url_base.rstrip("/")
            self.booru_tools.destination_plugin.URL_BASE = url_base

        self.blacklisted_tags = [tag for tag in blacklisted_tags.split(",") if tag != ""]
        self.required_tags = [tag for tag in required_tags.split(",") if tag != ""]
        self.allowed_blank_pages = allowed_blank_pages
        self.download_page_size = download_page_size

    async def run(self, *args, **kwargs):
        await self.post_init(*args, **kwargs)

        for url in self.urls:
            try:
                await self._import_posts_from_url(url)
            except Exception as e:
                logger.critical(f"url import failed with {e}")

        await self.booru_tools.update_tags(tags=self.all_tags)
        
        self.booru_tools.cleanup_process_directories()
        await self.booru_tools.session_manager.close()

    async def _import_posts_from_url(self, url:str):
        self.gallery_dl = GalleryDl(
            tmp_path=self.booru_tools.tmp_directory,
            urls=[url]
        )

        metadata_downloader = self.gallery_dl.create_bulk_downloader(
            only_metadata=True,
            download_count=self.download_page_size
        )
        
        for download_folder in metadata_downloader:
            posts = await self._ingest_folder(folder=download_folder)
            post_count = len(posts)
            try:
                await self.booru_tools.update_posts(posts=posts)
            except TypeError as e:
                logger.warning(f"Error updating posts due to {e}")
            self.booru_tools.delete_directory(directory=download_folder)
            if self._check_download_limit_reached(post_count=post_count):
                break
    
    async def _ingest_folder(self, folder:Path) -> list[resources.InternalPost]:
        metadata_list = self.booru_tools.import_metadata_files(download_directory=folder)
        logger.debug(f"Reviewing the metadata of {len(metadata_list)} files")

        posts_to_download:list[resources.InternalPost] = []
        all_posts:list[resources.InternalPost] = []
        
        for metadata in metadata_list:
            post:resources.InternalPost = self.booru_tools.create_post_from_metadata(metadata=metadata, download_link="")
            
            if post.contains_any_tags(tags=self.blacklisted_tags):
                logger.info(f"Skipping '{post.id}' as it contains blacklisted tags from {self.blacklisted_tags}")
                continue
            if not post.contains_all_tags(tags=self.required_tags):
                logger.info(f"Skipping '{post.id}' as it does not contain all required tags from {self.required_tags}")
                continue

            all_posts.append(post)

            existing_post = await self.booru_tools.destination_plugin.find_exact_post(post=post)
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
@click.option('--required-tags', type=str, default="", help="A comma seperated list of tags to require on all posts")
@click.option('--match-source/--ignore-source', default=True, help="Whether post source should be used when importing")
@click.option('--allowed-blank-pages', type=int, default=1, help="Number of pages to download post pages before stopping")
@click.option('--plugin-override', type=str, help="Provide plugin override values")
@click.option('--download-page-size', type=int, default=100, help="The number of posts to download per page")
# Need to add something to require specific ratings as these aren't generally tags
def cli(*args, **kwargs):
    command = ImportPostsCommand()
    asyncio.run(command.run(*args, **kwargs))