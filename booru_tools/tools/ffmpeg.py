from pathlib import Path
from loguru import logger
import subprocess
import json

from booru_tools.shared import resources, constants

# My thoughts are that we can use this as a part of some post download image processing for post meta data
# Things like tagging webm/video for webm files, mp4 files etc, tagging with things like duration_over_60_seconds, sound

class FFmpeg:
    _SUPPORTED_FILE_EXTENSIONS = [
        ".webm", 
        ".mp4",
        ".mkv"
    ]

    @classmethod
    def add_video_tags(cls, post:resources.InternalPost) -> resources.InternalPost:
        if not post.local_file:
            logger.debug(f"Post {post.id} has no local file, skipping ffmpeg tagging")
            return post
        
        if not cls._check_file_supported(post.local_file):
            logger.debug(f"File {post.local_file} is not supported for video tagging")
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

        logger.debug(f"Generating audio tags for {ffmpeg_json['format']['filename']}")
        post.tags.extend(cls._generate_audio_tags(ffmpeg_json))

        logger.debug(f"Generating video tags for {ffmpeg_json['format']['filename']}")
        duration_tags = cls._generate_video_duration_tags(ffmpeg_json)
        post.tags.extend(duration_tags)
        post.tags.append(resources.InternalTag(names=["video"], category=constants.TagCategory.META))

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

        return audio_tags

    @classmethod
    def _generate_video_duration_tags(cls, ffmpeg_json:dict) -> list[resources.InternalTag]:
        logger.debug(f"Generating duration tags for {ffmpeg_json['format']['filename']}")
        duration = int(
            float(ffmpeg_json["format"]["duration"])
        )

        duration_chunks = int(duration // 30)
        second_blocks = [30 * (i + 1) for i in range(duration_chunks)]

        duration_tags:list[resources.InternalTag] = []
        
        for second_block in second_blocks:
            logger.debug(f"Duration block: {second_block}")
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
            
            tag = resources.InternalTag(
                names=names,
                category=constants.TagCategory.META,
                implications=[tag for tag in duration_tags]
            )

            duration_tags.append(tag)

        return duration_tags

    @classmethod
    def _check_file_supported(cls, file:Path) -> bool:
        is_file_supported = file.suffix in cls._SUPPORTED_FILE_EXTENSIONS
        return is_file_supported