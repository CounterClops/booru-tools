from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
import shutil
from typing import Callable, Generator
from urllib.parse import urljoin, urlparse

from loguru import logger

from booru_tools.downloaders import _base
from booru_tools.shared import config


class YtDlpManager(_base.DownloadManager):
    def __init__(
        self,
        *,
        extra_params: list[str] | None = None,
        url_resolver: Callable[[str], list[str]] | None = None,
        metadata_enricher: Callable[[dict], dict] | None = None,
        metadata_id_resolver: Callable[[dict], str] | None = None,
    ):
        logger.debug(f"Loading {self.__class__.__name__}")
        self.extra_params: list[str] = list(extra_params or [])
        self.url_resolver = url_resolver
        self.metadata_enricher = metadata_enricher
        self.metadata_id_resolver = metadata_id_resolver
        self._downloaded_links: list[str] = []

        config_manager = config.shared_config_manager
        cookies_file: Path = config_manager["networking"]["cookies_file"]
        self.page_size: int = config_manager["downloaders"]["gallery_dl"]["page_size"]
        self.ignored_file_extensions: list[str] = config_manager["downloaders"]["gallery_dl"]["ignored_file_extensions"]
        self.no_download: bool = config_manager["downloaders"]["gallery_dl"]["no_download"]

        if cookies_file:
            logger.debug(f"Using cookies file '{cookies_file}'")
            self.extra_params.extend([
                "--cookies",
                f"{cookies_file}",
            ])

    def _run_yt_dlp(self, params: list[str], *, check: bool = False) -> subprocess.CompletedProcess:
        command = [
            "yt-dlp",
            *self.extra_params,
            *params,
        ]
        logger.debug(f"Running command: {' '.join(command)}")
        return subprocess.run(command, capture_output=True, text=True, check=check)

    @staticmethod
    def _normalise_candidate_url(url: str, *, base_url: str) -> str:
        if not isinstance(url, str):
            return ""

        stripped_url = url.strip()
        if not stripped_url:
            return ""

        if stripped_url.startswith("//"):
            stripped_url = f"https:{stripped_url}"
        elif not stripped_url.startswith(("http://", "https://")):
            stripped_url = urljoin(base_url, stripped_url)

        parsed = urlparse(stripped_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        return stripped_url

    def _extract_flat_playlist_video_urls(self, url: str) -> list[str]:
        params = [
            "--flat-playlist",
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            url,
        ]

        result = self._run_yt_dlp(params)
        if result.returncode != 0:
            logger.debug(f"yt-dlp flat playlist extraction failed for '{url}' with rc={result.returncode}")
            return []

        if not result.stdout.strip():
            return []

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.debug(f"yt-dlp returned non-JSON payload while flat-extracting '{url}'")
            return []

        entries = data.get("entries") or []
        found_urls: list[str] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            for key in ["webpage_url", "original_url", "url"]:
                candidate = self._normalise_candidate_url(entry.get(key), base_url=url)
                if candidate:
                    found_urls.append(candidate)
                    break

        return list(dict.fromkeys(found_urls))

    def _resolve_video_urls(self, url: str) -> list[str]:
        flat_playlist_urls = self._extract_flat_playlist_video_urls(url=url)
        if flat_playlist_urls:
            return flat_playlist_urls

        if self.url_resolver:
            try:
                resolved_urls = [
                    candidate
                    for candidate in self.url_resolver(url)
                    if isinstance(candidate, str) and candidate.strip()
                ]
                if resolved_urls:
                    return list(dict.fromkeys(resolved_urls))
            except Exception as error:
                logger.warning(f"Custom yt-dlp URL resolver failed for '{url}' due to {error}")

        candidate = self._normalise_candidate_url(url, base_url=url)
        return [candidate] if candidate else []

    @staticmethod
    def _normalise_metadata_identifier(raw_value: str) -> str:
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw_value).strip())
        return candidate.strip("-._")

    @classmethod
    def _derive_metadata_id_from_urls(cls, metadata: dict) -> str:
        for key in ["webpage_url", "original_url", "url"]:
            raw_url = str(metadata.get(key, "") or "").strip()
            if not raw_url:
                continue

            parsed = urlparse(raw_url)
            path_segments = [segment for segment in parsed.path.split("/") if segment]
            if not path_segments:
                continue

            identifier = cls._normalise_metadata_identifier(path_segments[-1])
            if identifier:
                return identifier

        return ""

    def _extract_metadata(self, video_url: str) -> dict | None:
        params = [
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            "--no-warnings",
            video_url,
        ]
        result = self._run_yt_dlp(params)
        if result.returncode != 0:
            logger.warning(f"Unable to extract metadata for '{video_url}'")
            return None

        payload = result.stdout.strip()
        if not payload:
            return None

        try:
            metadata = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(f"Invalid metadata JSON returned by yt-dlp for '{video_url}'")
            return None

        if self.metadata_enricher:
            try:
                metadata = self.metadata_enricher(metadata)
            except Exception as error:
                logger.warning(f"Custom metadata enricher failed for '{video_url}' due to {error}")

        return metadata

    def _get_metadata_id(self, metadata: dict) -> str:
        if self.metadata_id_resolver:
            try:
                custom_identifier = self._normalise_metadata_identifier(self.metadata_id_resolver(metadata))
                if custom_identifier:
                    return custom_identifier
            except Exception as error:
                logger.warning(f"Custom metadata ID resolver failed due to {error}")

        direct_identifiers = [
            metadata.get("id"),
            metadata.get("display_id"),
            metadata.get("uploader_id"),
        ]
        for direct_identifier in direct_identifiers:
            normalised_identifier = self._normalise_metadata_identifier(str(direct_identifier or ""))
            if normalised_identifier:
                return normalised_identifier

        url_derived_identifier = self._derive_metadata_id_from_urls(metadata)
        if url_derived_identifier:
            return url_derived_identifier

        extractor_name = self._normalise_metadata_identifier(str(metadata.get("extractor_key") or metadata.get("extractor") or ""))
        fallback_payload = json.dumps(metadata, sort_keys=True, default=str)
        fallback_hash = hashlib.sha1(fallback_payload.encode("utf-8")).hexdigest()[:16]
        if extractor_name:
            return f"{extractor_name}-{fallback_hash}"
        return fallback_hash

    def download_info(self, urls: list[str], download_directory: Path) -> list[_base.DownloadItem]:
        download_directory.mkdir(parents=True, exist_ok=True)

        resolved_video_urls: list[str] = []
        for url in urls:
            resolved_video_urls.extend(self._resolve_video_urls(url=url))

        resolved_video_urls = list(dict.fromkeys(resolved_video_urls))
        logger.debug(f"Resolved {len(resolved_video_urls)} yt-dlp URLs")

        items: list[_base.DownloadItem] = []
        for video_url in resolved_video_urls:
            metadata = self._extract_metadata(video_url=video_url)
            if not metadata:
                continue

            try:
                metadata_id = self._get_metadata_id(metadata)
            except ValueError as e:
                logger.warning(f"Skipping metadata due to {e}")
                continue

            metadata_file = (download_directory / f"{metadata_id}.json").absolute()
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            item = _base.DownloadItem(
                metadata_file=metadata_file,
                _download_override=video_url,
            )
            items.append(item)

        return items

    def download_pending_items(self, job: _base.DownloadJob) -> _base.DownloadJob:
        for item in job.download_items:
            if item.resource and item.resource.post_url:
                item.download_url = item.resource.post_url
            else:
                item.download_url = item._download_override

        if self.no_download:
            logger.debug("No download flag is set, skipping media download")
            return job

        urls_to_download: list[str] = []
        for item in job.items_pending_download():
            if item.ignore:
                continue

            if item.download_url in self._downloaded_links:
                item.media_download_desired = False
                continue

            if item.download_url:
                urls_to_download.append(item.download_url)
                job._downloaded_links.append(item.download_url)

        if not urls_to_download:
            logger.debug("No media files to download")
            return job

        output_template = str(job.download_folder / "%(id)s.%(ext)s")
        params = [
            "--no-warnings",
            "--no-playlist",
            "--output",
            output_template,
            *urls_to_download,
        ]

        result = self._run_yt_dlp(params)
        if result.returncode != 0:
            logger.warning("yt-dlp media download failed for one or more items")

        for item in job.download_items:
            if not item.media_download_desired:
                continue

            file_stem = item.metadata_file.stem
            possible_files = [
                file
                for file in item.metadata_file.parent.glob(f"{file_stem}.*")
                if file.suffix.lower() != ".json"
            ]

            if not possible_files:
                continue

            media_file = sorted(possible_files, key=lambda p: p.stat().st_size, reverse=True)[0]
            if media_file.suffix.lower() in self.ignored_file_extensions:
                item.media_download_desired = False
                continue

            item.media_file = media_file
            if item.resource:
                item.resource.local_file = media_file

        return job

    def create_download_job(self, params: list[str]) -> _base.DownloadJob:
        temp_folder = self.create_temp_folder()
        download_items = self.download_info(params, temp_folder)

        return _base.DownloadJob(
            download_folder=temp_folder,
            download_items=download_items,
            _download_manager=self,
        )

    def download(self, url: str, skip_every_second_page: bool = False) -> Generator[_base.DownloadJob, None, None]:
        del skip_every_second_page

        self._downloaded_links = []

        temp_folder = self.create_temp_folder()
        temp_folder.mkdir(parents=True, exist_ok=True)
        metadata_cache_folder = temp_folder / "metadata-cache"
        metadata_cache_folder.mkdir(parents=True, exist_ok=True)

        download_items = self.download_info([url], metadata_cache_folder)

        # Keep yt-dlp behavior efficient by extracting metadata once, then yielding scoped jobs.
        # page_size=0 keeps prior "single batch" behavior.
        chunk_size = self.page_size if self.page_size and self.page_size > 0 else len(download_items)

        if not download_items:
            logger.debug(f"No yt-dlp metadata items discovered for '{url}'")
        else:
            logger.debug(
                f"Yielding yt-dlp download jobs in chunks of {chunk_size} "
                f"for {len(download_items)} discovered items"
            )

        for start_index in range(0, len(download_items), chunk_size):
            scoped_items = download_items[start_index:start_index + chunk_size]
            chunk_index = (start_index // chunk_size) + 1
            chunk_folder = temp_folder / f"chunk-{chunk_index:04d}"
            chunk_folder.mkdir(parents=True, exist_ok=True)

            job_items: list[_base.DownloadItem] = []
            for item in scoped_items:
                chunk_metadata_file = chunk_folder / item.metadata_file.name
                shutil.move(str(item.metadata_file), str(chunk_metadata_file))

                job_items.append(_base.DownloadItem(
                    metadata_file=chunk_metadata_file,
                    _download_override=item._download_override,
                ))

            logger.debug(
                f"Yielding yt-dlp scoped job with {len(scoped_items)} items "
                f"(offset={start_index})"
            )

            job = _base.DownloadJob(
                download_folder=chunk_folder,
                download_items=job_items,
                _download_manager=self,
            )
            yield job
            self._downloaded_links.extend(job._downloaded_links)

        self._downloaded_links = []
        return