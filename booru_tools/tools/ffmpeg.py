from pathlib import Path
from loguru import logger
import subprocess
import json

from booru_tools.shared import resources, constants, config

# My thoughts are that we can use this as a part of some post download image processing for post meta data
# Things like tagging webm/video for webm files, mp4 files etc, tagging with things like duration_over_60_seconds, sound

class FFmpeg:
    _SUPPORTED_FILE_EXTENSIONS = [
        ".webm", 
        ".mp4",
        ".mkv"
    ]
    _BLOCK_SIZE_SECONDS = 30

    @classmethod
    def add_video_tags(cls, post:resources.InternalPost) -> resources.InternalPost:
        config_manager = config.shared_config_manager
        
        if not config_manager["tools"]["ffmpeg"]["enabled"]:
            logger.debug(f"FFmpeg is disabled, skipping video tagging")
            return post

        if not post.local_file:
            logger.debug(f"Post {post.id} has no local file, skipping ffmpeg tagging")
            return post
        
        if not cls._check_file_supported(post.local_file):
            logger.debug(f"File {post.local_file} is not supported for video tagging")
            return post
        
        if not cls._check_ffmpeg_installed():
            logger.warning(f"FFmpeg is not installed, unable to create video tags")
            return post
        
        command = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(post.local_file.absolute())
        ]

        command_output = subprocess.run(
            command,
            capture_output=True,
            encoding='utf-8'
        )

        if command_output.returncode != 0:
            logger.error(f"Failed to run command {command}")
            return post
        
        logger.debug(f"Loading JSON from ffprobe output")
        ffmpeg_json = json.loads(command_output.stdout)

        if config_manager["tools"]["ffmpeg"]["create_basic_video_tags"]:
            logger.debug(f"Generating audio/video tags for {ffmpeg_json['format']['filename']}")

            post.tags.extend(
                cls._generate_audio_tags(ffmpeg_json)
            )
            post.tags.extend(
                cls._generate_video_framerate_tags(ffmpeg_json)
            )
            post.tags.extend(
                cls._generate_video_resolution_tags(ffmpeg_json)
            )

            post.tags.append(resources.InternalTag(names=["video"], category=constants.TagCategory.META))

        if config_manager["tools"]["ffmpeg"]["create_duration_tags"]:
            logger.debug(f"Generating video duration tags for {ffmpeg_json['format']['filename']}")
            duration_tags = cls._generate_video_duration_tags(ffmpeg_json)
            post.tags.extend(duration_tags)

        if config_manager["tools"]["ffmpeg"]["create_ffmpeg_processed_tag"]:
            post.tags.append(
                resources.InternalTag(names=["ffmpeg_processed"], category=constants.TagCategory.META)
            )

        return post

    @classmethod
    def _generate_audio_tags(cls, ffmpeg_json:dict) -> list[resources.InternalTag]:
        logger.debug(f"Generating audio tags for {ffmpeg_json['format']['filename']}")
        audio_tags = []
        
        audio_streams = {
            key: stream
            for key, stream in enumerate(ffmpeg_json["streams"])
            if stream["codec_type"] == "audio"
        }

        audio_stream_count = len(audio_streams)
        if audio_stream_count > 0:
            logger.debug(f"Found {audio_stream_count} audio streams")
            audio_tags.append(resources.InternalTag(names=["sound"], category=constants.TagCategory.META))
        else:
            logger.debug(f"Found no audio streams")
            audio_tags.append(resources.InternalTag(names=["no_sound"], category=constants.TagCategory.META))

        return audio_tags

    @classmethod
    def _generate_video_duration_tags(cls, ffmpeg_json:dict) -> list[resources.InternalTag]:
        logger.debug(f"Generating duration tags for {ffmpeg_json['format']['filename']}")
        duration = int(
            float(ffmpeg_json["format"]["duration"])
        )

        duration_chunks = int(duration // cls._BLOCK_SIZE_SECONDS)
        second_blocks = [cls._BLOCK_SIZE_SECONDS * (i + 1) for i in range(duration_chunks)]

        logger.debug(f"Video duration is {duration} seconds with {duration_chunks} {cls._BLOCK_SIZE_SECONDS} second blocks")
        duration_tags:list[resources.InternalTag] = []
        
        for second_block in second_blocks:
            logger.debug(f"Processing duration block {second_block}")
            names = []

            if second_block < 100:
                names.append(f"longer_than_{second_block}_seconds")
            
            if second_block % 60 == 0:
                minute = int(second_block / 60)
                if minute > 5:
                    if minute % 10 == 0:
                        names.append(f"longer_than_{minute}_minutes")
                else:
                    names.append(f"longer_than_{minute}_minute{"s" if second_block > 60 else ""}")
            
            if not names:
                logger.debug(f"No tags for duration block {second_block}, skipping")
                continue

            tag_implications = [tag for tag in duration_tags]
            tag = resources.InternalTag(
                names=names,
                category=constants.TagCategory.META,
                implications=tag_implications
            )

            duration_tags.append(tag)

        return duration_tags
    
    @classmethod
    def _generate_video_framerate_tags(cls, ffmpeg_json:dict) -> list[resources.InternalTag]:
        video_stream = cls._get_primary_video_stream(ffmpeg_json)
        avg_frame_rate = video_stream.get("avg_frame_rate", "30/1")
        framerate = int(avg_frame_rate.split("/")[0])
        if framerate >= 48:
            tags = [
                resources.InternalTag(names=["high_framerate"], category=constants.TagCategory.META)
            ]
            return tags
        return []

    @classmethod
    def _generate_video_resolution_tags(cls, ffmpeg_json:dict) -> list[resources.InternalTag]:
        tags = []
        video_stream = cls._get_primary_video_stream(ffmpeg_json)
        height = video_stream.get("height", 0)
        width = video_stream.get("width", 0)

        if height == 0 or width == 0:
            return tags
        
        for tag_string in constants.ImageResolutionTags.get_tag_strings(height=height, width=width):
            tags.append(
                resources.InternalTag(names=[tag_string], category=constants.TagCategory.META)
            )
        return tags

    @staticmethod
    def _get_primary_video_stream(ffmpeg_json:dict[str, list[dict]]) -> dict:
        video_streams = [
            stream 
            for stream in ffmpeg_json["streams"] 
            if stream.get("codec_type", "unknown") == "video"
        ]
        primary_video_stream = video_streams[0]
        return primary_video_stream

    @classmethod
    def _check_file_supported(cls, file:Path) -> bool:
        is_file_supported = file.suffix in cls._SUPPORTED_FILE_EXTENSIONS
        return is_file_supported
    
    @classmethod
    def _check_ffmpeg_installed(cls) -> bool:
        command = ["ffprobe", "-version"]
        try:
            command_output = subprocess.run(
                command,
                capture_output=True,
                encoding='utf-8'
            )
        except FileNotFoundError:
            return False

        logger.debug(f"Confirmed ffprobe installed")
        return command_output.returncode == 0