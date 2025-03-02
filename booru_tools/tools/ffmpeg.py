from pathlib import Path
from loguru import logger
import subprocess
import json
import re

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
        
        try:
            ffmpeg_json = cls._get_ffmpeg_json(file=post.local_file)
        except Exception as e:
            logger.error(f"Failed to get ffmpeg json for {post.local_file} with {e}")
            return post

        if config_manager["tools"]["ffmpeg"]["create_basic_video_tags"]:
            logger.debug(f"Generating audio/video tags for {ffmpeg_json['format']['filename']}")

            post = cls._remove_existing_audio_tags(post)
            post.tags.extend(
                cls._generate_audio_tags(ffmpeg_json, file=post.local_file)
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
    def _get_ffmpeg_json(cls, file:Path) -> dict:
        ffmpeg_json = cls._extract_ffmpeg_json(file=file)
        try:
            if cls._validate_ffmpeg_json(ffmpeg_json):
                return ffmpeg_json
        except KeyError:
            logger.error(f"Failed to validate ffmpeg json for original file {file.name}")
        
        new_file = cls._remux_file(file=file.absolute())
        ffmpeg_json = cls._extract_ffmpeg_json(file=new_file)
        if cls._validate_ffmpeg_json(ffmpeg_json):
            return ffmpeg_json

    @classmethod
    def _remux_file(cls, file:Path) -> Path:
        new_file = Path(file.parent.absolute() / file.with_suffix(".remux.mkv"))
        logger.info(f"Remuxing file {file.name} to {new_file.name} to extract metadata")
        remux_command = [
            "ffmpeg",
            "-i", str(file),
            "-c", "copy",
            "-y",
            str(new_file)
        ]

        command_output = subprocess.run(
            remux_command,
            capture_output=True,
            encoding='utf-8'
        )
        
        if command_output.returncode != 0:
            logger.error(f"Failed to run remux command {remux_command}")
            raise Exception(f"Failed to run command {remux_command} with {command_output.stderr}")

        return new_file
    
    @classmethod
    def _extract_ffmpeg_json(cls, file:Path) -> dict:
        command_base = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams"
        ]

        extract_command = [
            *command_base,
            str(file.absolute())
        ]

        command_output = subprocess.run(
            extract_command,
            capture_output=True,
            encoding='utf-8'
        )

        if command_output.returncode != 0:
            logger.error(f"Failed to run command {extract_command} with {command_output.stdout}")
            raise Exception(f"Failed to run command {extract_command} ")
        
        logger.debug(f"Loading JSON from ffprobe output")
        ffmpeg_json = json.loads(command_output.stdout)
        return ffmpeg_json

    @classmethod
    def _validate_ffmpeg_json(cls, ffmpeg_json:dict) -> bool:
        try:
            ffmpeg_json["format"]["duration"]
            ffmpeg_json["streams"]
        except KeyError as e:
            logger.debug(f"Failed to validate ffmpeg json {ffmpeg_json} with {e}")
            raise KeyError
        
        return True
    
    @staticmethod
    def _remove_existing_audio_tags(post:resources.InternalPost) -> resources.InternalPost:
        ffmpeg_tags = [
            "sound", 
            "no_sound"
        ]

        for tag in post.tags:
            for tag_name in tag.names:
                if tag_name in ffmpeg_tags:
                    post.tags.remove(tag)
        
        return post
        

    @classmethod
    def _generate_audio_tags(cls, ffmpeg_json:dict, file:Path) -> list[resources.InternalTag]:
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
            if cls._check_for_audible_sound(file):
                audio_tags.append(resources.InternalTag(names=["sound"], category=constants.TagCategory.META))
            else:
                audio_tags.append(resources.InternalTag(names=["no_sound"], category=constants.TagCategory.META))
        else:
            logger.debug(f"Found no audio streams")
            audio_tags.append(resources.InternalTag(names=["no_sound"], category=constants.TagCategory.META))

        return audio_tags

    @staticmethod
    def _check_for_audible_sound(file:Path) -> bool:
        logger.debug(f"Checking for audible sound in {file.name}")
        command = [
            "ffmpeg", "-i", str(file.absolute()), "-af", "volumedetect", "-hide_banner", "-vn", "-sn", "-dn", "-f", "null", "/dev/null"
        ]

        command_output = subprocess.run(
            command,
            capture_output=True,
            encoding='utf-8'
        )

        if command_output.returncode != 0:
            logger.error(f"Failed to run command {command}")
            raise Exception(f"Failed to run command {command}")

        # Parse the output to find mean_volume and max_volume
        mean_volume = re.search(r'mean_volume: ([\-\d.]+) dB', command_output.stderr)
        max_volume = re.search(r'max_volume: ([\-\d.]+) dB', command_output.stderr)

        if mean_volume and max_volume:
            mean_volume = float(mean_volume.group(1))
            max_volume = float(max_volume.group(1))
        else:
            logger.warning(f"Could not detect volume for {file.name}")
            return False

        logger.debug(f"mean_volume: {mean_volume}, max_volume: {max_volume}")
        audio_threshold = -30
        if mean_volume < audio_threshold and max_volume < audio_threshold:
            logger.info(f"Audio track found in {file.name}, but audio is likely silent as {mean_volume} under the threshold of {audio_threshold}")
            return False
        
        logger.debug(f"Audio track found in {file.name} with mean volume {mean_volume} and max volume {max_volume}")
        return True


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
        ffprobe_command = ["ffprobe", "-version"]
        try:
            ffprobe_command_output = subprocess.run(
                ffprobe_command,
                capture_output=True,
                encoding='utf-8'
            )
        except FileNotFoundError:
            return False

        logger.debug(f"Confirmed ffprobe installed")

        ffmpeg_installed = ffprobe_command_output.returncode == 0

        ffmpeg_command = ["ffmpeg", "-version"]
        try:
            ffmpeg_command_output = subprocess.run(
                ffmpeg_command,
                capture_output=True,
                encoding='utf-8'
            )
        except FileNotFoundError:
            return False

        logger.debug(f"Confirmed ffmpeg installed")

        ffmpeg_installed = ffmpeg_command_output.returncode == 0

        return ffmpeg_installed and ffmpeg_installed