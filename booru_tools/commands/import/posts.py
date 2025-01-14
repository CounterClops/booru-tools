from loguru import logger
from pathlib import Path
from urllib.parse import urlparse
import click
import asyncio
import traceback

from booru_tools import core
from booru_tools.shared import resources, constants
from booru_tools.plugins import _plugin_template
from booru_tools.tools.gallery_dl import GalleryDl


class ImportPostsCommand():
    def __init__(self):
        self.blank_download_page_count = 0
        self.all_tags:list[resources.InternalTag] = []
    
    async def post_init(self, 
                destination:str, 
                url:list[str]=[], 
                import_site:str="", 
                urls_file:Path=None, 
                cookies:Path=None, 
                blacklisted_tags:str="", 
                required_tags:str="", 
                allowed_blank_pages:int=1, 
                match_source:bool=True, 
                plugin_override:str="", 
                download_page_size:int=100,
                allowed_safety:str="",
                minimum_score:int=0
            ):
        booru_config = {
            "destination": destination
        }
        
        self.booru_tools = core.BooruTools(
            config=booru_config
        )

        if plugin_override:
            self.booru_tools.override_plugin_config(
                plugin=self.booru_tools.destination_plugin,
                plugin_override=plugin_override
            )
        
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

        # Maybe expand this out to get tags from the destination plugin and populate aliases. Extra toggle maybe?
        self.blacklisted_tags = self.booru_tools.split_tag_list(blacklisted_tags)
        self.required_tags = self.booru_tools.split_tag_list(required_tags)
        self.allowed_blank_pages = allowed_blank_pages
        self.download_page_size = download_page_size
        self.minimum_score = minimum_score

        self.allowed_safety = []
        for safety in allowed_safety.split(","):
            standard_safety = constants.Safety.get_matching_safety(safety=safety, return_default=False)
            if standard_safety:
                self.allowed_safety.append(standard_safety)

    async def run(self, *args, **kwargs):
        await self.post_init(*args, **kwargs)
        processed_posts = []

        for url in self.urls:
            async for job in self.download_posts_from_url(url):
                posts = [item.resource for item in job.download_items if item.ignore == False]
                try:
                    processed_posts.extend([post.id for post in posts])
                    await self.booru_tools.update_posts(posts=posts)
                except Exception as e:
                    logger.critical(f"url import failed with {e}")
                    logger.critical(traceback.format_exc())
                finally:
                    job.cleanup_folders()

        # filtered_tags = self._filter_tags(tags=self.all_tags)
        # await self.booru_tools.update_tags(tags=filtered_tags)
        # self.all_tags = []
        
        self.booru_tools.cleanup_process_directories()
        await self.booru_tools.session_manager.close()
    
    def _filter_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalTag]:
        filtered_tags = [tag for tag in tags if tag.category != constants.TagCategory._DEFAULT]
        logger.debug(f"Filtered out tags in default category, going from {len(tags)} tags to {len(filtered_tags)} tags")
        return filtered_tags

    def check_for_allowed_post(self, post:resources.InternalPost):
        if not self.check_post_allowed(post=post):
            logger.info(f"Skipping '{post.id}' as it is not allowed with current config")
            return False
        return True

    async def download_posts_from_url(self, url:str):
        domain:str = urlparse(url).hostname

        meta_plugin:_plugin_template.MetadataPlugin = self.booru_tools.metadata_loader.load_matching_plugin(domain=domain)
        api_plugin:_plugin_template.ApiPlugin = self.booru_tools.api_loader.load_matching_plugin(domain=domain)
        validator_plugins:list[_plugin_template.ValidationPlugin] = self.booru_tools.validation_loader.load_all_plugins()

        for job in meta_plugin.DOWNLOAD_MANAGER.download(url=url):
            for item in job.download_items:
                plugins = resources.InternalPlugins(
                    api=api_plugin,
                    meta=meta_plugin,
                    validators=validator_plugins
                )
                metadata_file = item.metadata_file
                post = meta_plugin.from_metadata_file(metadata_file=metadata_file, plugins=plugins)

                item.resource = post

                if not self.check_for_allowed_post(post=post):
                    logger.debug(f"Marking post '{post.id}' as something to be ignored")
                    item.ignore = True
                    continue

                for tag in post.tags:
                    if tag in self.all_tags:
                        continue
                    self.all_tags.append(tag)
            
            posts = [item.resource for item in job.download_items if item.ignore == False]
            existing_post_tasks = await self._check_for_existing_posts(posts=posts)
            
            for item in job.download_items:
                if item.ignore:
                    continue

                existing_post:resources.InternalPost = existing_post_tasks[item.resource.id].result()
                if existing_post:
                    post:resources.InternalPost = existing_post.merge_resource(update_object=post, deep_copy=False)
                else:
                    item.media_download_desired = True

            job.download_media()
            yield job

    def check_post_allowed(self, post:resources.InternalPost):
        if post.contains_any_tags(tags=self.blacklisted_tags):
            logger.debug(f"Post '{post.id}' contains blacklisted tags from {self.blacklisted_tags}")
            return False
        if not post.contains_all_tags(tags=self.required_tags):
            logger.debug(f"Post '{post.id}' does not contain all required tags from {self.required_tags}")
            return False
        if self.allowed_safety and (post.safety not in self.allowed_safety):
            logger.debug(f"Post '{post.id}' is not in the allowed safety selection from {self.allowed_safety}")
            return False
        if self.minimum_score and post.score < self.minimum_score:
            logger.debug(f"Post '{post.id}' has a score of {post.score} which is below the minimum score of {self.minimum_score}")
            return False
        if post.deleted:
            logger.debug(f"Post '{post.id}' is marked as deleted")
            return False
        logger.debug(f"Post '{post.id}' passed all checks")
        return True

    async def _check_for_existing_posts(self, posts:list[resources.InternalPost]) -> dict[int, asyncio.Task]:
        existing_posts:dict[int, asyncio.Task] = {}
        async with asyncio.TaskGroup() as task_group:
            for post in posts:
                task = task = task_group.create_task(
                    self.booru_tools.find_exact_post(post=post)
                )
                existing_posts[post.id] = task
        return existing_posts

@click.command()
@click.option('--url', multiple=True, help='URL to import from')
@click.option('--import-site', multiple=True, help='The site name or domain to import from')
@click.option('--urls-file', multiple=True, type=Path, help='A file containing URLs to import')
@click.option('--destination', default="szurubooru", help='Where to send the new posts to')
@click.option('--cookies', type=Path, help='The cookies to use for this download')
@click.option('--blacklisted-tags', type=str, default="", help="A comma seperated list of tags to blacklist, you can specify an AND condition with |")
@click.option('--required-tags', type=str, default="", help="A comma seperated list of tags to require on all posts, you can specify an AND condition with |")
@click.option('--minimum-score', type=int, default=0, help="The minimum score a post must have to be imported")
@click.option('--match-source/--ignore-source', default=True, help="Whether post source should be used when importing")
@click.option('--allowed-blank-pages', type=int, default=1, help="Number of pages to download post pages before stopping")
@click.option('--plugin-override', type=str, help="Provide plugin override values")
@click.option('--download-page-size', type=int, default=100, help="The number of posts to download per page")
@click.option('--allowed-safety', type=str, default="", help=f"The comma seperated list of allowed safety ratings from [{constants.Safety.SAFE},{constants.Safety.SKETCHY},{constants.Safety.UNSAFE}]")
# Need to add something to require specific ratings as these aren't generally
def cli(*args, **kwargs):
    command = ImportPostsCommand()
    asyncio.run(command.run(*args, **kwargs))