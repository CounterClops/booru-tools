import importlib.util
from pathlib import Path
import click

def load_commands(cli:click.Group, folder:Path=Path("commands")):
    for file in folder.glob("*"):
        if file.name.startswith("_"):
            continue

        if file.is_dir():
            group_name = file.stem
            group_cmd = click.Group()
            load_commands(cli=group_cmd, folder=file.absolute())
            cli.add_command(group_cmd, name=group_name)
            continue

        if not file.name.endswith(".py"):
            continue
        
        module_name = file.stem
        spec = importlib.util.spec_from_file_location(module_name, file.absolute())
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        cli.add_command(module.cli, name=module_name)