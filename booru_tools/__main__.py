# from booru_tools.core import BooruTools

# booru_tools = BooruTools()
# booru_tools.sync(
#     urls=[
#         "https://e621.net/posts/3052115",
#         # "https://e621.net/pools/36579",
#         # "https://e621.net/posts/1150307",
#         # "https://e621.net/pools/36579",
#         "https://e621.net/posts?tags=claweddrip+female+-male_on_male",
#     ]
# )

import click
from pathlib import Path

from booru_tools.loaders import command_loader

if __name__ == "__main__":
    command_group = click.Group()
    command_folder = Path(__file__).parent / Path("commands")
    command_loader.load_commands(cli=command_group, folder=command_folder)
    command_group()