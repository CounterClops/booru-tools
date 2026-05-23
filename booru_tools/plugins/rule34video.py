from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from loguru import logger

from booru_tools.downloaders import ytp_dl
from booru_tools.plugins import _plugin_template
from booru_tools.shared import config
from booru_tools.shared import constants, resources


def _normalise_tag_name(raw_name: str) -> str:
    return raw_name.strip().lower().replace(" ", "_")


def _append_tag_if_missing(tags: list[resources.InternalTag], name: str, category: str) -> None:
    normalised_name = _normalise_tag_name(name)
    if not normalised_name:
        return

    for tag in tags:
        if normalised_name in tag.names:
            return

    tags.append(resources.InternalTag(names=[normalised_name], category=category))


class SharedAttributes:
    _DOMAINS = [
        "rule34video.com",
    ]
    _CATEGORY = [
        "rule34video",
    ]
    _NAME = "rule34video"

    URL_BASE = "https://rule34video.com"

    REQUIRE_SOURCE_CHECK = True

    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/latest-updates"

    @property
    def DOWNLOAD_MANAGER(self):
        try:
            return self._downloader
        except (AttributeError, NotImplementedError):
            pass

        self._downloader = ytp_dl.YtDlpManager()
        return self._downloader


class Rule34VideoMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def _resolve_webpage_url(self, metadata: dict) -> str:
        for key in ["webpage_url", "original_url", "url"]:
            candidate = str(metadata.get(key, "") or "").strip()
            if candidate.startswith("http") and "rule34video.com" in candidate:
                return candidate

        post_id = str(metadata.get("id", "") or "").strip()
        if post_id.isdigit():
            return f"{self.URL_BASE}/video/{post_id}/"

        return ""

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

    def _build_cookie_header(self, domain: str = "rule34video.com") -> str:
        config_manager = config.shared_config_manager
        cookies_file: Path = config_manager["networking"]["cookies_file"]
        if not cookies_file:
            return ""

        try:
            cookie_jar = MozillaCookieJar()
            cookie_jar.load(cookies_file, ignore_discard=True, ignore_expires=True)
        except Exception as e:
            logger.debug(f"Rule34Video fallback could not load cookies from '{cookies_file}' due to {e}")
            return ""

        cookie_parts: list[str] = []
        for cookie in cookie_jar:
            if domain not in (cookie.domain or ""):
                continue
            cookie_parts.append(f"{cookie.name}={cookie.value}")

        return "; ".join(cookie_parts)

    def _extract_like_candidates_from_text(self, text: str) -> list[int]:
        candidates: list[int] = []
        if not text:
            return candidates

        # Common site format: 55% (222)
        for match in re.findall(r"\(([\d.,]+[KM]?)\)", text, flags=re.IGNORECASE):
            parsed = self._parse_compact_count(match)
            if parsed:
                candidates.append(parsed)

        # Generic likes/votes patterns
        for match in re.findall(r"([\d.,]+[KM]?)\s*(?:likes?|votes?)\b", text, flags=re.IGNORECASE):
            parsed = self._parse_compact_count(match)
            if parsed:
                candidates.append(parsed)

        return candidates

    def _extract_like_count_from_html(self, html: str) -> int:
        if not html:
            return 0

        candidates: list[int] = []

        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: known vote container classes
        selector_candidates = [
            ".voters.count",
            ".rating-container .count",
            "[class*='voters'][class*='count']",
            "[class*='rating'][class*='count']",
        ]
        for selector in selector_candidates:
            for element in soup.select(selector):
                element_text = element.get_text(" ", strip=True)
                candidates.extend(self._extract_like_candidates_from_text(element_text))

        # Strategy 2: metadata attributes on voting controls
        for element in soup.select("[data-up-score], [data-up-users], [data-vote]"):
            for attribute_name in ["data-up-score", "data-up-users"]:
                value = element.get(attribute_name)
                parsed = self._parse_compact_count(str(value)) if value else 0
                if parsed:
                    candidates.append(parsed)

        # Strategy 3: context-aware regex from raw HTML for markup drift
        regex_patterns = [
            r"class=['\"][^'\"]*voters[^'\"]*count[^'\"]*['\"][^>]*>(.*?)</",
            r"class=['\"][^'\"]*rating[^'\"]*count[^'\"]*['\"][^>]*>(.*?)</",
            r"([\d.,]+[KM]?)\s*(?:likes?|votes?)\b",
            r"\d+\s*%\s*\(([\d.,]+[KM]?)\)",
        ]
        for pattern in regex_patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE | re.DOTALL):
                if isinstance(match, tuple):
                    match = " ".join([part for part in match if part])
                candidates.extend(self._extract_like_candidates_from_text(str(match)))

        if not candidates:
            return 0

        # Avoid tiny percentages and pick the highest plausible count.
        return max(candidates)

    def _get_webpage_html(self, metadata: dict) -> str:
        webpage_url = self._resolve_webpage_url(metadata=metadata)
        if not webpage_url:
            logger.debug("Rule34Video HTML fallback skipped: resolved webpage URL is empty")
            return ""

        html_cache = self.__dict__.get("_webpage_html_cache")
        if html_cache is None:
            html_cache = {}
            self._webpage_html_cache = html_cache

        if webpage_url in html_cache:
            cached_html = html_cache[webpage_url] or ""
            logger.debug(
                f"Rule34Video HTML fallback cache hit for '{webpage_url}' with {len(cached_html)} bytes"
            )
            return html_cache[webpage_url]

        logger.debug(f"Rule34Video HTML fallback cache miss for '{webpage_url}', requesting page")

        try:
            request_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Referer": self.URL_BASE,
            }
            cookie_header = self._build_cookie_header(domain="rule34video.com")
            if cookie_header:
                request_headers["Cookie"] = cookie_header

            request = Request(webpage_url, headers=request_headers)
            with urlopen(request, timeout=30) as response:
                final_url = response.geturl()
                html = response.read().decode("utf-8", errors="ignore")
                status_code = getattr(response, "status", "unknown")

            logger.debug(
                f"Rule34Video HTML fallback response for '{webpage_url}': status={status_code}, "
                f"final_url='{final_url}', bytes={len(html)}"
            )

            if "rule34video.com" not in final_url:
                logger.debug(f"Rule34Video fallback was redirected away from source to '{final_url}'")
                return ""
        except Exception as e:
            logger.debug(f"Rule34Video fallback request failed for '{webpage_url}' due to {e}")
            return ""

        html_cache[webpage_url] = html
        return html

    def _extract_artist_uploader_from_html(self, html: str) -> tuple[list[str], list[str]]:
        if not html:
            return [], []

        soup = BeautifulSoup(html, "html.parser")
        artists: list[str] = []
        uploaders: list[str] = []

        # Primary source: structured model suggestion section.
        for element in soup.select("[data-suggest-type='model'] a.item .name"):
            artist_name = element.get_text(" ", strip=True)
            if artist_name and artist_name not in artists:
                artists.append(artist_name)

        # Fallback source: JS payload with video_models.
        for match in re.findall(r"video_models\s*:\s*'([^']*)'", html, flags=re.IGNORECASE):
            for artist_name in match.split(","):
                artist_name = artist_name.strip()
                if artist_name and artist_name not in artists:
                    artists.append(artist_name)

        # Uploaded by section can use slightly different wrappers.
        for label_element in soup.select("div.label"):
            label_text = label_element.get_text(" ", strip=True).lower()
            if "uploaded by" not in label_text:
                continue

            col = label_element.find_parent("div", class_="col")
            if not col:
                continue

            uploader_item = col.select_one("a.item")
            if not uploader_item:
                continue

            uploader_name = uploader_item.get_text(" ", strip=True)
            if uploader_name and uploader_name not in uploaders:
                uploaders.append(uploader_name)

        # Additional fallback source from yt-dlp extraction conventions.
        uploader = soup.select_one(".uploader .name")
        if uploader:
            uploader_name = uploader.get_text(" ", strip=True)
            if uploader_name and uploader_name not in uploaders:
                uploaders.append(uploader_name)

        return artists, uploaders

    def _fetch_like_count(self, metadata: dict) -> int:
        webpage_url = self._resolve_webpage_url(metadata=metadata)
        post_id = metadata.get("id", "unknown")
        if not webpage_url:
            logger.debug(f"Rule34Video likes fallback failed for post '{post_id}': no source URL available")
            return 0

        logger.debug(f"Rule34Video likes fallback requesting URL '{webpage_url}' for post '{post_id}'")

        try:
            html = self._get_webpage_html(metadata=metadata)
        except Exception as e:
            logger.debug(
                f"Rule34Video likes fallback failed for post '{post_id}': exception while fetching HTML from "
                f"'{webpage_url}' due to {e}\n{traceback.format_exc()}"
            )
            return 0

        if not html:
            logger.debug(
                f"Rule34Video likes fallback failed for post '{post_id}': empty HTML response from '{webpage_url}'"
            )
            return 0

        try:
            like_count = self._extract_like_count_from_html(html=html)
        except Exception as e:
            logger.debug(
                f"Rule34Video likes fallback failed for post '{post_id}': exception while parsing HTML from "
                f"'{webpage_url}' due to {e}\n{traceback.format_exc()}"
            )
            return 0

        if not like_count:
            logger.debug(
                f"Rule34Video likes fallback failed for post '{post_id}': no like candidates found in HTML from '{webpage_url}'"
            )
            return 0

        logger.debug(
            f"Rule34Video likes fallback parsed value {like_count} for post '{post_id}' from '{webpage_url}'"
        )
        return like_count

    def get_id(self, metadata: dict) -> int:
        raw_id = str(metadata.get("id", "")).strip()
        if raw_id.isdigit():
            return int(raw_id)

        post_url = self.get_post_url(metadata=metadata)
        match = re.search(r"/videos?/(\d+)", post_url)
        if match:
            return int(match.group(1))

        raise ValueError("Unable to determine Rule34Video post id")

    def get_sources(self, metadata: dict) -> list[str]:
        sources: list[str] = []

        for key in ["webpage_url", "original_url", "uploader_url", "url"]:
            source = metadata.get(key)
            if source and source not in sources:
                sources.append(source)

        post_url = self.get_post_url(metadata=metadata)
        if post_url and post_url not in sources:
            sources.append(post_url)

        return sources

    def get_description(self, metadata: dict) -> str:
        return metadata.get("description", "") or ""

    def get_score(self, metadata: dict) -> int:
        for key in ["score", "like_count", "likes", "vote_count"]:
            value = metadata.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        post_id = metadata.get("id", "unknown")
        logger.debug(f"Rule34Video score missing for post '{post_id}', attempting likes fallback")
        like_count = self._fetch_like_count(metadata=metadata)
        if like_count:
            logger.debug(f"Rule34Video likes fallback succeeded for post '{post_id}' with value {like_count}")
            return like_count
        logger.debug(f"Rule34Video likes fallback found no score for post '{post_id}'")
        return 0

    def get_tags(self, metadata: dict[str, Any]) -> list[resources.InternalTag]:
        all_tags: list[resources.InternalTag] = []

        for tag_name in metadata.get("tags") or []:
            _append_tag_if_missing(
                tags=all_tags,
                name=tag_name,
                category=constants.TagCategory.GENERAL,
            )

        for category_name in metadata.get("categories") or []:
            _append_tag_if_missing(
                tags=all_tags,
                name=category_name,
                category=constants.TagCategory.GENERAL,
            )

        for creator_name in metadata.get("creators") or []:
            _append_tag_if_missing(
                tags=all_tags,
                name=creator_name,
                category=constants.TagCategory.ARTIST,
            )

        uploader = metadata.get("uploader")
        if uploader:
            _append_tag_if_missing(
                tags=all_tags,
                name=uploader,
                category=constants.TagCategory.ARTIST,
            )

        has_artist_tag = any(tag.category == constants.TagCategory.ARTIST for tag in all_tags)
        if not has_artist_tag:
            html = self._get_webpage_html(metadata=metadata)
            artist_names, uploader_names = self._extract_artist_uploader_from_html(html=html)

            if artist_names or uploader_names:
                logger.debug(
                    f"Rule34Video artist fallback found artists={artist_names} uploaders={uploader_names} "
                    f"for post '{metadata.get('id', 'unknown')}'"
                )

            for artist_name in artist_names:
                _append_tag_if_missing(
                    tags=all_tags,
                    name=artist_name,
                    category=constants.TagCategory.ARTIST,
                )

            for uploader_name in uploader_names:
                _append_tag_if_missing(
                    tags=all_tags,
                    name=uploader_name,
                    category=constants.TagCategory.ARTIST,
                )

        return all_tags

    def get_created_at(self, metadata: dict) -> datetime:
        timestamp = metadata.get("timestamp")
        if timestamp:
            return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)

        upload_date = str(metadata.get("upload_date", "")).strip()
        if upload_date:
            return datetime.strptime(upload_date, "%Y%m%d")

        raise NotImplementedError

    def get_updated_at(self, metadata: dict) -> datetime:
        return self.get_created_at(metadata=metadata)

    def get_safety(self, metadata: dict) -> str:
        age_limit = metadata.get("age_limit")
        if age_limit is not None and int(age_limit) >= 18:
            return constants.Safety.UNSAFE
        return constants.Safety.SAFE

    def get_post_url(self, metadata: dict) -> str:
        post_url = metadata.get("webpage_url") or metadata.get("original_url") or ""
        if post_url:
            return post_url

        post_id = self.get_id(metadata=metadata)
        return f"{self.URL_BASE}/video/{post_id}/"

    def get_deleted(self, metadata: dict) -> bool:
        return False


class Rule34VideoValidator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"https?://(?:www\.)?rule34video\.com/videos?/\d+(?:/[^\s\"'#?]+)?/?", re.IGNORECASE)
    USER_URL_PATTERN = re.compile(r"https?://(?:www\.)?rule34video\.com/members?/\d+(?:/[^\s\"'#?]+)?/?", re.IGNORECASE)
    GLOBAL_URL_PATTERN = re.compile(r"https?://(?:www\.)?rule34video\.com(?:/.*)?$", re.IGNORECASE)

    def get_source_type(self, url: str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.USER_URL_PATTERN.match(url):
            return constants.SourceTypes.AUTHOR
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT
