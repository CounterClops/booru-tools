from dataclasses import dataclass, field
from pathlib import Path

@dataclass(kw_only=True)
class DefaultConfigBaseGroup:
    pass

### Core
@dataclass(kw_only=True)
class DefaultCoreConfig(DefaultConfigBaseGroup):
    blacklisted_tags:list = field(default_factory=list, metadata={"description": "A list of blacklisted tags to avoid"})
    required_tags:list = field(default_factory=list, metadata={"description": "A list of required tags to enforce"})
    allowed_safety:list = field(default_factory=lambda: ["safe", "sketchy", "unsafe"], metadata={"description": "A list of the allowed post safety levels"})
    minimum_score:int = field(default=10, metadata={"description": "The minimum score a post must have to be processed"})
    destination:str = field(default="szurubooru", metadata={"description": "The destination plugin to use"})
    add_video_metatags:bool = field(default=False, metadata={"description": "Whether to add video metadata tags to posts using ffmpeg"})
    cleanup_temp_directories:bool = field(default=True, metadata={"description": "Whether to cleanup temporary directories after running"})
    update_tag_categories:bool = field(default=True, metadata={"description": "Whether to update tag categories"})

### Commands
@dataclass(kw_only=True)
class DefaultCommandsImportPostsConfig(DefaultConfigBaseGroup):
    urls:list = field(default_factory=list)
    import_site:str = field(default=None)

@dataclass(kw_only=True)
class DefaultCommandsImportConfig(DefaultConfigBaseGroup):
    posts:DefaultCommandsImportPostsConfig = field(default_factory=DefaultCommandsImportPostsConfig)

@dataclass(kw_only=True)
class DefaultCommandsConfig(DefaultConfigBaseGroup):
    migrate:DefaultCommandsImportConfig = field(default_factory=DefaultCommandsImportConfig)

### Downloaders
@dataclass(kw_only=True)
class DefaultDownloadersGalleryDlConfig(DefaultConfigBaseGroup):
    page_size:int = field(default=50)
    allowed_blank_pages:int = field(default=1)
    no_download:bool = field(default=False)
    extra_params:list = field(default_factory=list)
    ignored_file_extensions:list[str] = field(default_factory=lambda: [".zip"])

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

### Tools
@dataclass(kw_only=True)
class DefaultToolsFfmpegConfig(DefaultConfigBaseGroup):
    enabled:bool = field(default=True)
    create_duration_tags:bool = field(default=True)
    create_basic_video_tags:bool = field(default=True)
    create_ffmpeg_processed_tag:bool = field(default=True)

@dataclass(kw_only=True)
class DefaultToolsConfig(DefaultConfigBaseGroup):
    ffmpeg:DefaultToolsFfmpegConfig = field(default_factory=DefaultToolsFfmpegConfig)

### Default Config
@dataclass(kw_only=True)
class DefaultConfig(DefaultConfigBaseGroup):
    core:DefaultCoreConfig = field(default_factory=DefaultCoreConfig)
    commands:DefaultCommandsConfig = field(default_factory=DefaultCommandsConfig)
    downloaders:DefaultDownloadersConfig = field(default_factory=DefaultDownloadersConfig)
    networking:DefaultNetworkingConfig = field(default_factory=DefaultNetworkingConfig)
    plugins:DefaultPluginsConfig = field(default_factory=DefaultPluginsConfig)
    tools:DefaultToolsConfig = field(default_factory=DefaultToolsConfig)