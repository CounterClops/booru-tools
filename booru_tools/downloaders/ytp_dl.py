from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Generator
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from loguru import logger

from booru_tools.downloaders import _base
from booru_tools.shared import config


class YtDlpManager(_base.DownloadManager):
    POST_URL_PATTERN = re.compile(r"https?://(?:www\.)?rule34video\.com/videos?/\d+(?:/[^\s\"'#?]+)?/?", re.IGNORECASE)

    def __init__(self, *, extra_params: list[str] | None = None):
        logger.debug(f"Loading {self.__class__.__name__}")
        self.extra_params: list[str] = list(extra_params or [])
        self._downloaded_links: list[str] = []

        config_manager = config.shared_config_manager
        cookies_file: Path = config_manager["networking"]["cookies_file"]
        self.page_size: int = config_manager["downloaders"]["gallery_dl"]["page_size"]
        self.allowed_blank_pages: int = config_manager["downloaders"]["gallery_dl"]["allowed_blank_pages"]
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

    def _normalise_video_url(self, url: str) -> str:
        if not url:
            return ""

        parsed = urlparse(url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else url

        if clean_url.startswith("//"):
            clean_url = f"https:{clean_url}"

        if not clean_url.startswith("http"):
            clean_url = urljoin("https://rule34video.com", clean_url)

        if self.POST_URL_PATTERN.match(clean_url):
            return clean_url.rstrip("/") + "/"
        return ""

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

            candidate = (
                entry.get("webpage_url")
                or entry.get("original_url")
                or entry.get("url")
            )

            candidate = self._normalise_video_url(candidate)
            if candidate:
                found_urls.append(candidate)
                continue

            entry_id = str(entry.get("id", "")).strip()
            if entry_id.isdigit():
                found_urls.append(f"https://rule34video.com/video/{entry_id}/")

        return list(dict.fromkeys(found_urls))

    def _discover_video_urls_from_page(self, url: str) -> list[str]:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (booru-tools)"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="ignore")

        raw_links = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        found_urls: list[str] = []

        for raw_link in raw_links:
            normalised_url = self._normalise_video_url(raw_link)
            if normalised_url:
                found_urls.append(normalised_url)

        return list(dict.fromkeys(found_urls))

    def _resolve_video_urls(self, url: str) -> list[str]:
        direct_url = self._normalise_video_url(url)
        if direct_url:
            return [direct_url]

        flat_playlist_urls = self._extract_flat_playlist_video_urls(url=url)
        if flat_playlist_urls:
            return flat_playlist_urls

        try:
            discovered_urls = self._discover_video_urls_from_page(url=url)
        except Exception as e:
            logger.warning(f"Unable to discover post URLs from '{url}' due to {e}")
            return []

        return discovered_urls

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

        return self._enrich_rule34video_metadata(metadata=metadata)

    @staticmethod
    def _parse_compact_count(value: str) -> int:
        if value is None:
            return 0

        compact_value = value.strip().replace(",", "").replace(" ", "").upper()
        if not compact_value:
            return 0

        multiplier = 1
        if compact_value.endswith("K"):
            multiplier = 1_000
            compact_value = compact_value[:-1]
        elif compact_value.endswith("M"):
            multiplier = 1_000_000
            compact_value = compact_value[:-1]

        try:
            return int(float(compact_value) * multiplier)
        except ValueError:
            return 0

    def _extract_like_count_from_page(self, webpage_url: str) -> int:
        if not webpage_url:
            return 0

        try:
            request = Request(webpage_url, headers={"User-Agent": "Mozilla/5.0 (booru-tools)"})
            with urlopen(request, timeout=30) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"Unable to fetch '{webpage_url}' for like_count fallback due to {e}")
            return 0

        patterns = [
            r'class="voters\s+count"[^>]*>([^<]+)<',
            r"class='voters\s+count'[^>]*>([^<]+)<",
            r'"icon-thumbs-up"[^<]*<span>([^<]+)</span>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if not match:
                continue

            like_count = self._parse_compact_count(match.group(1))
            if like_count:
                return like_count

        return 0

    def _enrich_rule34video_metadata(self, metadata: dict) -> dict:
        if not isinstance(metadata, dict):
            return metadata

        raw_like_count = metadata.get("like_count")
        like_count = int(raw_like_count or 0)

        if like_count <= 0:
            webpage_url = metadata.get("webpage_url") or metadata.get("original_url") or ""
            like_count = self._extract_like_count_from_page(webpage_url=webpage_url)
            if like_count:
                metadata["like_count"] = like_count

        if like_count:
            metadata["score"] = like_count

        return metadata

    def _get_metadata_id(self, metadata: dict) -> str:
        metadata_id = str(metadata.get("id", "")).strip()
        if metadata_id:
            return metadata_id

        webpage_url = metadata.get("webpage_url") or metadata.get("original_url") or ""
        match = re.search(r"/videos?/(\d+)", webpage_url)
        if match:
            return match.group(1)

        raise ValueError("Unable to determine post id from yt-dlp metadata")

    def download_info(self, urls: list[str], download_directory: Path) -> list[_base.DownloadItem]:
        download_directory.mkdir(parents=True, exist_ok=True)

        resolved_video_urls: list[str] = []
        for url in urls:
            resolved_video_urls.extend(self._resolve_video_urls(url=url))

        resolved_video_urls = list(dict.fromkeys(resolved_video_urls))
        logger.debug(f"Resolved {len(resolved_video_urls)} Rule34Video URLs")

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
        job = self.create_download_job([url])
        yield job

        self._downloaded_links = []
        return