from loguru import logger
from pathlib import Path
from urllib.parse import urlparse
import click
import asyncio
import traceback

from booru_tools import core
from booru_tools.shared import resources, constants, errors
from booru_tools.plugins import _plugin_template

class MigratePostsCommand():
    def __init__(self):
        self.blank_download_page_count = 0
    
    async def post_init(self,
                destination:str,
                url:list[str]=[],
                import_site:str="",
                urls_file:Path=None,
                cookies:Path=None,
                blacklisted_tags:str=None,
                required_tags:str=None,
                allowed_blank_pages:int=1,
                match_source:bool=True,
                plugin_override:str="",
                download_page_size:int=100,
                allowed_safety:str=None,
                minimum_score:int=None,
                post_concurrency:int=None,
                large_file_size_mb:int=None,
                large_file_concurrency:int=None,
                transient_backoff_recovery_successes:int=None,
                cleanup_tmp:bool=True,
            ):
        
        self.booru_tools = core.BooruTools()
        
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
        
        self.booru_tools.set_options(
            blacklisted_tags=blacklisted_tags,
            required_tags=required_tags,
            allowed_safety=allowed_safety,
            minimum_score=minimum_score,
            cleanup_temp_directories=cleanup_tmp,
            post_update_concurrency=post_concurrency,
            large_file_size_mb=large_file_size_mb,
            large_file_concurrency=large_file_concurrency,
            transient_backoff_recovery_successes=transient_backoff_recovery_successes,
        )

        # Eagerly expand the blacklist to include all aliases + recursive implications
        # from the destination site so that check_post_allowed covers all known aliases.
        await self.booru_tools.expand_blacklist_tags()

    async def run(self, *args, **kwargs):
        await self.post_init(*args, **kwargs)
        processed_posts = []

        try:
            for url in self.urls:
                logger.info(f"Processing URL: {url}")
                url_post_count = 0
                try:
                    async for job in self.download_posts_from_url(url):
                        posts = [item.resource for item in job.download_items if item.ignore == False]
                        try:
                            url_post_count += len(posts)
                            processed_posts.extend([post.id for post in posts])
                            await self.booru_tools.update_posts(posts=posts)
                        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                            raise
                        except Exception as e:
                            logger.critical(f"url import failed with {e}")
                            logger.error(traceback.format_exc())
                        finally:
                            if self.booru_tools.cleanup_temp_directories:
                                job.cleanup_folders()
                except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    logger.error(f"Failed to process URL '{url}': {e}")
                    logger.error(traceback.format_exc())
                else:
                    logger.info(f"Finished URL '{url}': {url_post_count} posts queued for push")
        finally:
            self.booru_tools.cleanup_process_directories()
            try:
                await self.booru_tools.session_manager.close()
            except BaseException:
                pass

    def check_for_allowed_post(self, post:resources.InternalPost):
        if not self.booru_tools.check_post_allowed(post=post):
            logger.info(f"Skipping '{post.id}' as it is not allowed with current config")
            return False
        return True

    @errors.SuppressGeneratorIterationOnExceptions(
        exceptions=[errors.NoPluginFound]
    )
    async def download_posts_from_url(self, url:str, force_download:bool=False, skip_every_second_page:bool=False):
        domain:str = urlparse(url).hostname

        try:
            meta_plugin:_plugin_template.MetadataPlugin = self.booru_tools.metadata_loader.load_matching_plugin(domain=domain)
        except errors.NoPluginFound as e:
            logger.warning(f"Could not find a plugin for '{domain}', skipping import")
            yield e
            return
        
        try:
            api_plugin:_plugin_template.ApiPlugin = self.booru_tools.api_loader.load_matching_plugin(domain=domain)
        except errors.NoPluginFound as e:
            api_plugin = None
        
        try:
            validator_plugins:list[_plugin_template.ValidationPlugin] = self.booru_tools.validation_loader.load_all_plugins()
        except errors.NoPluginFound as e:
            validator_plugins = None

        for job in meta_plugin.DOWNLOAD_MANAGER.download(url=url, skip_every_second_page=skip_every_second_page):
            for item in job.download_items:
                plugins = resources.InternalPlugins(
                    api=api_plugin,
                    meta=meta_plugin,
                    validators=validator_plugins
                )
                metadata_file = item.metadata_file
                post = meta_plugin._from_metadata_file(metadata_file=metadata_file, plugins=plugins)

                item.resource = post

                if not self.check_for_allowed_post(post=post):
                    logger.debug(f"Marking post '{post.id}' as something to be ignored")
                    item.ignore = True
                    continue
            
            posts = [item.resource for item in job.download_items if item.ignore == False]
            existing_post_tasks = await self._check_for_existing_posts(posts=posts)
            
            for item in job.download_items:
                if item.ignore:
                    continue

                existing_post:resources.InternalPost = existing_post_tasks[item.resource.id].result()
                if existing_post:
                    post:resources.InternalPost = existing_post.merge_resource(update_object=post, deep_copy=False)
                    if force_download:
                        item.media_download_desired = True
                else:
                    item.media_download_desired = True

            total = len(job.download_items)
            filtered = sum(1 for item in job.download_items if item.ignore)
            new_posts = sum(1 for item in job.download_items if not item.ignore and item.media_download_desired)
            existing_posts = total - filtered - new_posts

            if total == 0:
                logger.warning("Page returned no metadata — gallery-dl may have failed or the search has no results")
            else:
                logger.info(
                    f"Page: {total} items — {new_posts} new (will download), "
                    f"{existing_posts} already in destination, {filtered} filtered"
                )

            job.download_media()
            yield job

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
@click.option('--post-concurrency', type=int, default=None, help="Max concurrent post pushes for normal-sized files")
@click.option('--large-file-size-mb', type=int, default=None, help="Size threshold in MB where post pushes switch to large-file mode")
@click.option('--large-file-concurrency', type=int, default=None, help="Max concurrent post pushes while handling large files")
@click.option('--transient-backoff-recovery-successes', type=int, default=None, help="Successful pushes required before restoring normal concurrency after transient failures")
@click.option('--cleanup-tmp/--no-cleanup-tmp', default=True, help='Whether temporary folders are deleted after the run')
@click.option('--allowed-safety', type=str, default="", help=f"The comma seperated list of allowed safety ratings from [{constants.Safety.SAFE},{constants.Safety.SKETCHY},{constants.Safety.UNSAFE}]")
# Need to add something to require specific ratings as these aren't generally
def cli(*args, **kwargs):
    command = MigratePostsCommand()
    asyncio.run(command.run(*args, **kwargs))