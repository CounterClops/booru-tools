import click
from pathlib import Path

from booru_tools.loaders import command_loader

if __name__ == "__main__":
    command_group = click.Group()
    command_folder = Path(__file__).parent / Path("commands")
    command_loader.load_commands(cli=command_group, folder=command_folder)
    command_group()