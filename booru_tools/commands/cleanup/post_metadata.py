from loguru import logger
from pathlib import Path
from urllib.parse import urlparse
import click
import asyncio
import traceback

from booru_tools import core
from booru_tools.shared import resources, constants
from booru_tools.plugins import _plugin_template
from booru_tools.commands.migrate.posts import MigratePostsCommand

class CleanupPostMetadataCommand(MigratePostsCommand):
    async def post_init(self, 
                url:list[str]=[]
            ):
        
        self.booru_tools = core.BooruTools()
        self.urls = url

    async def run(self, *args, **kwargs):
        await self.post_init(*args, **kwargs)
        processed_posts = []

        for url in self.urls:
            async for job in self.download_posts_from_url(url, force_download=True):
                posts = [item.resource for item in job.download_items if item.ignore == False]
                try:
                    processed_posts.extend([post.id for post in posts])
                    await self.booru_tools.update_posts(posts=posts)
                except Exception as e:
                    logger.critical(f"url import failed with {e}")
                    logger.critical(traceback.format_exc())
                finally:
                    job.cleanup_folders()
        
        self.booru_tools.cleanup_process_directories()
        await self.booru_tools.session_manager.close()

@click.command()
@click.option('--url', multiple=True, help='URL to import from')
def cli(*args, **kwargs):
    command = CleanupPostMetadataCommand()
    asyncio.run(command.run(*args, **kwargs))