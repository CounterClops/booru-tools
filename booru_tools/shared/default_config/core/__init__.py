from dataclasses import dataclass, field

@dataclass(kw_only=True)
class DefaultConfig:
    blacklisted_tags:list = field(
        default_factory=list, 
        metadata={
            "description": "A list of blacklisted tags to avoid"
        }
    )
    required_tags:list = field(
        default_factory=list,
        metadata={
            "description": "A list of required tags to enforce"
        }
    )
    allowed_safety:list = field(
        default_factory=lambda: ["safe", "sketchy", "unsafe"], 
        metadata={
            "description": "A list of the allowed post safety levels"
        }
    )
    minimum_score:int = field(
        default=10,
        metadata={
            "description": "The minimum score a post must have to be processed"
        }
    )
    destination:str = field(
        default="szurubooru",
        metadata={
            "description": "The destination plugin to use"
        }
    )
    add_video_metatags:bool = field(
        default=False,
        metadata={
            "description": "Whether to add video metadata tags to posts using ffmpeg"
        }
    )
    cleanup_temp_directories:bool = field(
        default=True, 
        metadata={
            "description": "Whether to cleanup temporary directories after running"
        }
    )
    update_tag_categories:bool = field(
        default=True,
        metadata={
            "description": "Whether to update tag categories"
        }
    )
    skip_every_second_page:bool = field(
        default=False,
        metadata={
            "description": "Whether to skip every second page when downloading"
        }
    )