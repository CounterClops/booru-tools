from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
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


def _parse_compact_count(value: str) -> int:
    if value is None:
        return 0

    compact_value = str(value).strip().replace(",", "").replace(" ", "").upper()
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


def _build_cookie_header(cookies_file: Path | None, *, domain: str) -> str:
    if not cookies_file:
        return ""

    cookies_path = Path(cookies_file)
    if not cookies_path.exists():
        return ""

    try:
        cookie_jar = MozillaCookieJar()
        cookie_jar.load(str(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as error:
        logger.debug(f"Rule34Video cookie load failed for '{cookies_file}' due to {error}")
        return ""

    cookie_pairs: list[str] = []
    for cookie in cookie_jar:
        cookie_domain = (cookie.domain or "").lstrip(".").lower()
        if not cookie_domain:
            continue

        if cookie_domain == domain or cookie_domain.endswith(f".{domain}"):
            cookie_pairs.append(f"{cookie.name}={cookie.value}")

    return "; ".join(cookie_pairs)


class Rule34VideoYtDlpAdapter:
    POST_URL_PATTERN = re.compile(r"https?://(?:www\.)?rule34video\.com/videos?/\d+(?:/[^\s\"'#?]+)?/?", re.IGNORECASE)
    DOMAIN = "rule34video.com"
    MAX_DISCOVERY_PAGES = 200

    def __init__(self, *, allowed_blank_pages: int, cookies_file: Path | None):
        self.allowed_blank_pages = allowed_blank_pages
        self.cookie_header = _build_cookie_header(cookies_file, domain=self.DOMAIN)

    def _normalise_video_url(self, url: str) -> str:
        if not isinstance(url, str):
            return ""

        stripped_url = url.strip()
        if not stripped_url:
            return ""

        if stripped_url.startswith("//"):
            stripped_url = f"https:{stripped_url}"
        elif not stripped_url.startswith(("http://", "https://")):
            stripped_url = urljoin("https://rule34video.com", stripped_url)

        parsed = urlparse(stripped_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if self.POST_URL_PATTERN.match(clean_url):
            return clean_url.rstrip("/") + "/"
        return ""

    def _canonicalise_listing_url(self, url: str, *, seed_url: str) -> str:
        parsed = urlparse(url)
        seed_parsed = urlparse(seed_url)

        query = parse_qs(parsed.query)
        canonical_query: dict[str, str] = {}

        for key, values in query.items():
            if not values:
                continue

            value = values[-1].strip()
            if not value:
                continue

            if key == "from":
                if not value.isdigit():
                    continue
                page_number = int(value)
                if page_number <= 1:
                    continue
                value = str(page_number)

            if key == "sort_by" and value == "post_date":
                continue

            canonical_query[key] = value

        canonical_query_string = urlencode(sorted(canonical_query.items()))
        canonical_path = parsed.path.rstrip("/") or "/"
        seed_path = seed_parsed.path.rstrip("/") or "/"

        if canonical_path == seed_path and not canonical_query_string:
            return seed_url

        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            canonical_query_string,
            "",
        ))

    def _fetch_html(self, url: str) -> str:
        request_headers = {
            "User-Agent": "Mozilla/5.0 (booru-tools)",
        }

        parsed = urlparse(url)
        if self.cookie_header and self.DOMAIN in parsed.netloc.lower():
            request_headers["Cookie"] = self.cookie_header

        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="ignore")

    def _extract_video_urls_from_html(self, html: str) -> list[str]:
        raw_links = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        resolved_urls: list[str] = []

        for raw_link in raw_links:
            post_url = self._normalise_video_url(raw_link)
            if post_url:
                resolved_urls.append(post_url)

        return list(dict.fromkeys(resolved_urls))

    def _extract_ajax_listing_page_urls(self, *, html: str, seed_url: str) -> list[str]:
        seed_parsed = urlparse(seed_url)
        ajax_page_urls: list[str] = []

        for data_parameters in re.findall(r'data-parameters="([^"]+)"', html, flags=re.IGNORECASE):
            query_params: dict[str, str] = {}
            for segment in data_parameters.split(";"):
                segment = segment.strip()
                if not segment or ":" not in segment:
                    continue

                key, value = segment.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    query_params[key] = value

            if "from" not in query_params:
                continue

            query = urlencode(query_params)
            ajax_url = urlunparse((
                seed_parsed.scheme,
                seed_parsed.netloc,
                seed_parsed.path,
                "",
                query,
                "",
            ))
            ajax_page_urls.append(self._canonicalise_listing_url(ajax_url, seed_url=seed_url))

        return list(dict.fromkeys(ajax_page_urls))

    def _extract_listing_page_urls(self, *, html: str, current_url: str, seed_url: str) -> list[str]:
        seed_parsed = urlparse(seed_url)
        seed_path = seed_parsed.path.rstrip("/") or "/"

        candidate_links = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        candidate_links.extend(
            re.findall(r"<link[^>]+rel=[\"']next[\"'][^>]+href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        )

        listing_pages: list[str] = []
        for raw_link in candidate_links:
            resolved_url = urljoin(current_url, raw_link)
            parsed = urlparse(resolved_url)

            if parsed.scheme not in {"http", "https"}:
                continue
            if self.DOMAIN not in parsed.netloc.lower():
                continue

            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url = f"{clean_url}?{parsed.query}"

            clean_url = self._canonicalise_listing_url(clean_url, seed_url=seed_url)

            if clean_url == current_url or self._normalise_video_url(clean_url):
                continue

            path_without_slash = parsed.path.rstrip("/")
            shares_seed_path = path_without_slash == seed_path or path_without_slash.startswith(f"{seed_path}/")
            if not shares_seed_path:
                continue

            query_keys = set(parse_qs(parsed.query).keys())
            has_pagination_marker = (
                bool(re.search(r"/page/\d+/?$", parsed.path))
                or "page" in query_keys
                or "from" in query_keys
                or "offset" in query_keys
            )
            if has_pagination_marker:
                listing_pages.append(clean_url)

        listing_pages.extend(self._extract_ajax_listing_page_urls(html=html, seed_url=seed_url))
        return list(dict.fromkeys(listing_pages))

    def _discover_video_urls_from_page(self, url: str) -> list[str]:
        queue: list[str] = [url]
        queued_pages: set[str] = {url}
        visited_pages: set[str] = set()
        discovered_post_urls: list[str] = []
        seen_post_urls: set[str] = set()
        blank_pages = 0

        while queue and len(visited_pages) < self.MAX_DISCOVERY_PAGES:
            page_url = queue.pop(0)
            if page_url in visited_pages:
                continue

            visited_pages.add(page_url)

            try:
                html = self._fetch_html(url=page_url)
            except Exception as error:
                logger.debug(f"Rule34Video fallback crawl failed to fetch '{page_url}' due to {error}")
                continue

            page_post_urls = self._extract_video_urls_from_html(html=html)
            new_page_post_urls = [post_url for post_url in page_post_urls if post_url not in seen_post_urls]

            if new_page_post_urls:
                discovered_post_urls.extend(new_page_post_urls)
                seen_post_urls.update(new_page_post_urls)
                blank_pages = 0
            else:
                blank_pages += 1
                if blank_pages > self.allowed_blank_pages:
                    break

            for next_page_url in self._extract_listing_page_urls(html=html, current_url=page_url, seed_url=url):
                if next_page_url in visited_pages or next_page_url in queued_pages:
                    continue
                queue.append(next_page_url)
                queued_pages.add(next_page_url)

        return list(dict.fromkeys(discovered_post_urls))

    def resolve_video_urls(self, url: str) -> list[str]:
        direct_url = self._normalise_video_url(url)
        if direct_url:
            return [direct_url]

        parsed = urlparse(url)
        if parsed.netloc and self.DOMAIN not in parsed.netloc.lower():
            return []

        try:
            return self._discover_video_urls_from_page(url=url)
        except Exception as error:
            logger.warning(f"Rule34Video fallback URL discovery failed for '{url}' due to {error}")
            return []

    def _extract_like_count_from_page(self, webpage_url: str) -> int:
        if not webpage_url:
            return 0

        try:
            html = self._fetch_html(webpage_url)
        except Exception as error:
            logger.debug(f"Rule34Video fallback could not fetch '{webpage_url}' for like_count due to {error}")
            return 0

        patterns = [
            r'class="voters\s+count"[^>]*>([^<]+)<',
            r"class='voters\s+count'[^>]*>([^<]+)<",
            r'"icon-thumbs-up"[^<]*<span>([^<]+)</span>',
            r"\d+\s*%\s*\(([\d.,]+[KM]?)\)",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if not match:
                continue

            like_count = _parse_compact_count(match.group(1))
            if like_count:
                return like_count

        return 0

    def enrich_metadata(self, metadata: dict) -> dict:
        if not isinstance(metadata, dict):
            return metadata

        raw_like_count = metadata.get("like_count")
        like_count = _parse_compact_count(raw_like_count)
        if like_count <= 0:
            webpage_url = str(metadata.get("webpage_url") or metadata.get("original_url") or "").strip()
            like_count = self._extract_like_count_from_page(webpage_url)
            if like_count:
                metadata["like_count"] = like_count

        if like_count:
            metadata["score"] = like_count

        return metadata

    def resolve_metadata_id(self, metadata: dict) -> str:
        raw_id = str(metadata.get("id", "") or "").strip()
        if raw_id:
            return raw_id

        webpage_url = str(metadata.get("webpage_url") or metadata.get("original_url") or "").strip()
        match = re.search(r"/videos?/(\d+)", webpage_url)
        if match:
            return match.group(1)

        return ""


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

        config_manager = config.shared_config_manager
        cookies_file: Path = config_manager["networking"]["cookies_file"]
        allowed_blank_pages: int = config_manager["downloaders"]["gallery_dl"]["allowed_blank_pages"]

        self._yt_dlp_adapter = Rule34VideoYtDlpAdapter(
            allowed_blank_pages=allowed_blank_pages,
            cookies_file=cookies_file,
        )
        self._downloader = ytp_dl.YtDlpManager(
            url_resolver=self._yt_dlp_adapter.resolve_video_urls,
            metadata_enricher=self._yt_dlp_adapter.enrich_metadata,
            metadata_id_resolver=self._yt_dlp_adapter.resolve_metadata_id,
        )
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
        return _parse_compact_count(value)

    def _build_cookie_header(self, domain: str = "rule34video.com") -> str:
        config_manager = config.shared_config_manager
        cookies_file: Path = config_manager["networking"]["cookies_file"]
        return _build_cookie_header(cookies_file, domain=domain)

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
