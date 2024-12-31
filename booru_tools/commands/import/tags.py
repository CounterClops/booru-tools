from loguru import logger
import click
import asyncio

from booru_tools import core
from booru_tools.shared import resources, errors
from booru_tools.plugins import _plugin_template

class ImportTagsCommand():
    async def post_init(
            self,
            only_related_tags:bool=False,
            import_site:str="",
            destination:str="",
            plugin_override:str=""
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
        
        self.found_import_plugins:list[_plugin_template.ApiPlugin] = []
        if import_site:
            for site_name in import_site:
                site_plugin:_plugin_template.ApiPlugin = self.booru_tools.api_loader.load_matching_plugin(name=site_name, domain=site_name, category=site_name)
                if site_plugin:
                    self.found_import_plugins.append(site_plugin)
        
        self.only_import_related_tags = only_related_tags

    async def run(self, *args, **kwargs):
        await self.post_init(*args, **kwargs)

        site_plugin_count = len(self.found_import_plugins)
        logger.debug(f"Found {site_plugin_count} plugins for site imports")
        
        for site_plugin in self.found_import_plugins:
            try:
                all_site_tags = await site_plugin.get_all_tags()
            except NotImplementedError as e:
                logger.info(f"Plugin {site_plugin._NAME} does not have get_all_tags implemented. Skipping site import")
                continue
            logger.info(f"Retrieved {len(all_site_tags)} tags from {site_plugin._NAME}")
            await self._import_tags(tags=all_site_tags)

    async def _import_tags(self, tags:list[resources.InternalTag]):
        if not self.only_import_related_tags:
            await self.booru_tools.update_tags(tags=tags)

@click.command()
@click.option("--only-related-tags", is_flag=True, help="Only import tags that have a relation to an existing tag")
@click.option('--import-site', multiple=True, help='The site name or domain to import from')
@click.option('--destination', default="szurubooru", help='Where to send the new tags to')
@click.option('--plugin-override', type=str, help="Provide plugin override values")
def cli(*args, **kwargs):
    command = ImportTagsCommand()
    asyncio.run(command.run(*args, **kwargs))