from dataclasses import dataclass, field

import commands
import core
import downloaders
import networking
import plugins
import tools

@dataclass(kw_only=True)
class DefaultConfig:
    commands:"commands.DefaultConfig" = field(
        default_factory=commands.DefaultConfig
    )
    core:"core.DefaultConfig" = field(
        default_factory=core.DefaultConfig
    )
    downloaders:... = field(
        default_factory=...
    )
    networking:... = field(
        default_factory=...
    )
    plugins:... = field(
        default_factory=...
    )
    tools:... = field(
        default_factory=...
    )