from dataclasses import dataclass, field
from pathlib import Path

@dataclass(kw_only=True)
class DefaultConfigBaseGroup:
    pass

### Core
@dataclass(kw_only=True)
class DefaultCoreConfig(DefaultConfigBaseGroup):
    blacklisted_tags:list = field(default_factory=list)
    required_tags:list = field(default_factory=list)
    allowed_safety:list = field(default_factory=lambda: ["safe", "sketchy", "unsafe"])
    minimum_score:int = field(default=10)
    destination:str = field(default="szurubooru")

### Commands
@dataclass(kw_only=True)
class DefaultCommandsImportPostsConfig(DefaultConfigBaseGroup):
    urls:list = field(default_factory=list)
    allowed_blank_pages:int = field(default=1)
    download_page_size:int = field(default=50)
    import_site:str = field(default=None)

@dataclass(kw_only=True)
class DefaultCommandsImportConfig(DefaultConfigBaseGroup):
    posts:DefaultCommandsImportPostsConfig = field(default_factory=DefaultCommandsImportPostsConfig)

@dataclass(kw_only=True)
class DefaultCommandsConfig(DefaultConfigBaseGroup):
    import_:DefaultCommandsImportConfig = field(default_factory=DefaultCommandsImportConfig)

### Downloaders
@dataclass(kw_only=True)
class DefaultDownloadersGalleryDlConfig(DefaultConfigBaseGroup):
    page_size:int = field(default=50)
    extra_params:list = field(default_factory=list)

@dataclass(kw_only=True)
class DefaultDownloadersConfig(DefaultConfigBaseGroup):
    gallery_dl:DefaultDownloadersGalleryDlConfig = field(default_factory=DefaultDownloadersGalleryDlConfig)

### Networking
@dataclass(kw_only=True)
class DefaultNetworkingConfig(DefaultConfigBaseGroup):
    connection_limit_per_host:int = field(default=5)
    cookies_file:Path = field(default=Path("cookies.txt"))

### Plugins
@dataclass(kw_only=True)
class DefaultPluginsSzurubooruConfig(DefaultConfigBaseGroup):
    username:str = field(default=None)
    password:str = field(default=None)
    URL_BASE:str = field(default=None)
    create_sql_fixes:bool = field(default=False)
    force_source_check:bool = field(default=True)

@dataclass(kw_only=True)
class DefaultPluginsConfig(DefaultConfigBaseGroup):
    szurubooru:DefaultPluginsSzurubooruConfig = field(default_factory=DefaultPluginsSzurubooruConfig)

### Default Config
@dataclass(kw_only=True)
class DefaultConfig(DefaultConfigBaseGroup):
    core:DefaultCoreConfig = field(default_factory=DefaultCoreConfig)
    commands:DefaultCommandsConfig = field(default_factory=DefaultCommandsConfig)
    downloaders:DefaultDownloadersConfig = field(default_factory=DefaultDownloadersConfig)
    networking:DefaultNetworkingConfig = field(default_factory=DefaultNetworkingConfig)
    plugins:DefaultPluginsConfig = field(default_factory=DefaultPluginsConfig)