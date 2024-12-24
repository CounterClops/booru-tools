# List supported sites for import
import click

from booru_tools import core

@click.command()
def cli():
    booru_tools = core.BooruTools()
    
    click.echo("Metadata Plugins:")
    for plugin in booru_tools.metadata_loader.plugins:
        click.echo(f"  {plugin.name}")

    click.echo("API Plugins:")
    for plugin in booru_tools.api_loader.plugins:
        click.echo(f"  {plugin.name}")

    click.echo("Validator Plugins:")
    for plugin in booru_tools.validation_loader.plugins:
        click.echo(f"  {plugin.name}")