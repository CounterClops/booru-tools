# List supported sites for import
import click
import inspect

from booru_tools import core
from booru_tools.plugins import _plugin_template

def get_custom_methods(cls) -> dict[str, object]:
    methods = {}
    for name, obj in inspect.getmembers(cls):
        if (inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.iscoroutinefunction(obj)) and not name.startswith("_"):
            methods[name] = obj
    return methods

def create_featureset_message(plugin:object, template:object) -> str:
    plugin_methods = get_custom_methods(plugin)
    template_methods = get_custom_methods(template)

    changed_methods = {}
    
    for method_name, base_method in template_methods.items():
        if method_name in plugin_methods:
            derived_method = plugin_methods[method_name]
            if base_method.__code__.co_code != derived_method.__code__.co_code:
                changed_methods[method_name] = derived_method
    
    supported_feature_count = f"{len(changed_methods)}/{len(template_methods)}"
    supported_feature_list = ", ".join([feature for feature in changed_methods.keys()])
    message = f": Supports {supported_feature_count} features [{supported_feature_list}]"
    return message

@click.command()
@click.option('--feature-set', is_flag=True, help='Listing the supported featureset of each plugin')
def cli(feature_set):
    booru_tools = core.BooruTools()
    
    click.echo("Metadata Plugins:")
    for plugin in booru_tools.metadata_loader.plugins:
        featureset_message = f""
        if feature_set:
            featureset_message = create_featureset_message(plugin=plugin.obj, template=_plugin_template.MetadataPlugin)
        click.echo(f"  {plugin.name} ({", ".join(plugin.obj._DOMAINS)}){featureset_message}")

    click.echo("API Plugins:")
    for plugin in booru_tools.api_loader.plugins:
        featureset_message = f""
        if feature_set:
            featureset_message = create_featureset_message(plugin=plugin.obj, template=_plugin_template.ApiPlugin)
        click.echo(f"  {plugin.name} ({", ".join(plugin.obj._DOMAINS)}){featureset_message}")

    click.echo("Validator Plugins:")
    for plugin in booru_tools.validation_loader.plugins:
        featureset_message = f""
        if feature_set:
            featureset_message = create_featureset_message(plugin=plugin.obj, template=_plugin_template.ValidationPlugin)
        click.echo(f"  {plugin.name} ({", ".join(plugin.obj._DOMAINS)}){featureset_message}")
