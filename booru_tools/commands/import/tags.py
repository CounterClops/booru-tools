from loguru import logger
import click
import asyncio

from booru_tools import core
from booru_tools.shared import resources
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

        all_tags = []
        for site_plugin in self.found_import_plugins:
            all_site_tags = await site_plugin.get_all_tags()
            all_tags.extend(all_site_tags)
        
        all_tags = self._filter_tags(tags=all_tags)
        print(all_tags)
        exit()
        self._import_tags(tags=all_tags)
    
    def merge_tags(self, current_tag:resources.InternalTag, new_tag:resources.InternalTag) -> resources.InternalTag:
        for tag_implication in new_tag.implications:
            if tag_implication not in current_tag:
                current_tag.implications.append(tag_implication)
        
        for name in new_tag.names:
            if name not in current_tag.names:
                current_tag.names.append(name)
        
        return current_tag
    
    async def _filter_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalTag]:
        all_tags = {}

        for tag in tags:
            tag_names = tag.names
            for name in tag_names:
                if name in all_tags:
                    current_tag = all_tags[name]
                    merged_tag = self.merge_tags(current_tag=current_tag, new_tag=tag)
                    for name in tag.names:
                        all_tags[name] = merged_tag
                    continue
                all_tags[name] = tag

        return all_tags.values()

    async def _import_tags(self, tags:list[resources.InternalTag]):
        if not self.only_import_related_tags:
            await self.booru_tools.update_tags(tags=tags)
            return
        
        for tag in tags:
            logger.debug(f"Importing {tag}")

            # found_tag:resources.InternalTag = self.booru_tools.destination_plugin.find_exact_tag(tag=tag)
            # if found_tag:
            #     found_tag = found_tag.create_merged_copy(update_object=tag)
            #     await self.booru_tools.destination_plugin.push_tag(tag=tag)
            #     continue
            
            # for tag_implication in tag.implications:
            #     found_tag:resources.InternalTag = self.booru_tools.destination_plugin.find_exact_tag(tag=tag)
            #     if found_tag:
            #         await self.booru_tools.destination_plugin.push_tag(tag=tag)
            #         break

@click.command()
@click.option("--only-related-tags", is_flag=True, help="Only import tags that have a relation to an existing tag")
@click.option('--import-site', multiple=True, help='The site name or domain to import from')
@click.option('--destination', default="szurubooru", help='Where to send the new tags to')
@click.option('--plugin-override', type=str, help="Provide plugin override values")
def cli(*args, **kwargs):
    command = ImportTagsCommand()
    asyncio.run(command.run(*args, **kwargs))