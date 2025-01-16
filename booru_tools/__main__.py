import click
from pathlib import Path

from booru_tools.loaders import command_loader
from booru_tools.shared import constants

if __name__ == "__main__":
    command_group = click.Group()
    command_folder = constants.ROOT_FOLDER / Path("commands")
    command_loader.load_commands(cli=command_group, folder=command_folder)
    command_group()