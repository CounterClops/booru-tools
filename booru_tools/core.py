from pathlib import Path
from loguru import logger
from http.cookiejar import MozillaCookieJar
from typing import Generator, Any
from datetime import datetime, timedelta, timezone
import json
import shutil
import hashlib
import asyncio
import aiohttp
import signal
import traceback

from booru_tools.loaders import plugin_loader
from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, resources, constants, config
from booru_tools.tools.ffmpeg import FFmpeg

class GracefulExit(SystemExit):
    code = 1

class SessionManager:
    def __init__(self, limit_per_host:int=10):
        self.session = None
        self.limit_per_host = limit_per_host
        self.default_headers = {
            "User-Agent": "BooruTools/1.0"
        }
        self.cookies = {}

    def start(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            limit_per_host=self.limit_per_host
        )
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.default_headers,
                skip_auto_headers=self.default_headers.keys(),
                connector=connector,
                cookies=self.cookies,
                raise_for_status=True
            )
        return self.session

    async def close(self):
        logger.debug("Closing aiohttp session")
        await self.session.close()

    def load_cookies(self, cookies:dict) -> None:
        """Update the session cookies with the provided cookies dictionary

        Args:
            cookies (dict): The cookies to update the HTTP session with
        """
        self.cookies = cookies

        if not self.session.closed:
            logger.debug(f"Updating session cookies with {len(cookies)} cookies")
            self.session.cookie_jar.update_cookies(cookies)
    
    def load_cookie_file(self, cookie_file:Path) -> dict:
        """The HTTP cookies to load from the provided file

        Args:
            cookie_file (Path): The HTTP cookies file to load

        Raises:
            FileNotFoundError: The provided cookie file does not exist
            ValueError: The provided cookie file was in an unsupported format

        Returns:
            dict: The cookies loaded from the file as a dictionary
        """
        cookies = {}

        if not cookie_file.exists():
            raise FileNotFoundError(f"Cookie file '{cookie_file}' does not exist")
        
        cookie_file = Path(cookie_file)

        if cookie_file.suffix == ".txt":
            logger.debug(f"Loading cookies from '{cookie_file}' with MozillaCookieJar")
            cookie_jar = MozillaCookieJar()
            cookie_jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
            for cookie in cookie_jar:
                cookies[cookie.name] = cookie.value
        elif cookie_file.suffix == ".json":
            logger.debug(f"Loading cookies from '{cookie_file}' with json")
            with open(cookie_file, "r") as f:
                cookies = json.load(f)
        else:
            raise ValueError("Unsupported file format. Only .txt and .json are supported.")

        self.load_cookies(cookies)
        return cookies

class BooruTools:
    def __init__(self, booru_plugin_directory:Path="", tmp_path:str="tmp"):
        if not booru_plugin_directory:
            program_path = constants.ROOT_FOLDER
            self.booru_plugin_directory = program_path / Path("plugins")
        else:
            self.booru_plugin_directory = Path(booru_plugin_directory)
        
        self.config = config.shared_config_manager
        self.tmp_directory = constants.TEMP_FOLDER

        self.cleanup_temp_directories = self.config["core"]["cleanup_temp_directories"]

        self.session_manager = SessionManager(
            limit_per_host=self.config["networking"].get("limit_per_host", 20)
        )

        signal.signal(signal.SIGINT, self.raise_graceful_exit)
        signal.signal(signal.SIGTERM, self.raise_graceful_exit)

        try:
            self.session_manager.start()
            cookie_file = self.config["networking"]["cookies_file"]
            if cookie_file:
                logger.debug(f"Attempting to load cookies from '{cookie_file}'")
                self.session_manager.load_cookie_file(
                    cookie_file=cookie_file
                )
        except RuntimeError as e:
            logger.debug(f"Error starting session due to {e}")
        self.load_plugins()

        # Expanded blacklist: populated by expand_blacklist_tags() with all aliases
        # of each simple string entry as individual OR strings.
        # None means not yet populated; populated list is used in check_post_allowed.
        self._expanded_blacklist: list | None = None
        # Per-tag alias map: {original_tag_name: [alias1, alias2, ...]}
        # Used by check_post_allowed to resolve AND-condition entries at check time.
        self._tag_aliases: dict | None = None

    def set_options(self,
            blacklisted_tags:str=None,
            required_tags:str=None,
            allowed_safety:str=None,
            minimum_score:str=None,
            add_video_metatags:str=None,
            cleanup_temp_directories:bool=None,
            update_tag_categories:str=None,
            skip_every_second_page:str=None,
            post_update_concurrency:int=None,
            large_file_size_mb:int=None,
            large_file_concurrency:int=None,
            transient_backoff_recovery_successes:int=None
        ) -> None:

        if blacklisted_tags:
            self.config["core"]["blacklisted_tags"] = self.split_tag_list(tag_string=blacklisted_tags)
        
        if required_tags:
            self.config["core"]["required_tags"] = self.split_tag_list(tag_string=required_tags)

        if allowed_safety:
            self.config["core"]["allowed_safety"] = allowed_safety.split(",")

        if minimum_score:
            self.config["core"]["minimum_score"] = int(minimum_score)

        if cleanup_temp_directories is not None:
            self.config["core"]["cleanup_temp_directories"] = bool(cleanup_temp_directories)
            self.cleanup_temp_directories = bool(cleanup_temp_directories)

        if post_update_concurrency is not None:
            self.config["core"]["post_update_concurrency"] = max(1, int(post_update_concurrency))

        if large_file_size_mb is not None:
            self.config["core"]["large_file_size_mb"] = max(1, int(large_file_size_mb))

        if large_file_concurrency is not None:
            self.config["core"]["large_file_concurrency"] = max(1, int(large_file_concurrency))

        if transient_backoff_recovery_successes is not None:
            self.config["core"]["transient_backoff_recovery_successes"] = max(1, int(transient_backoff_recovery_successes))
        

    def raise_graceful_exit(self, *args):
        """Raises a graceful exit exception to shutdown the program

        Raises:
            GracefulExit: The exception to raise to shutdown the program
        """
        try:
            for task in asyncio.all_tasks():
                task.cancel()
        except RuntimeError:
            logger.debug("No async loop when cancelling tasks")
        self.cleanup_process_directories()
        logger.info("Gracefully shutdown")
        raise GracefulExit()
    
    # def setup_logger(self) -> None:
    #     logger.configure()

    def load_plugins(self) -> None:
        """Loads the plugins for this instances set of loaders
        """
        self.metadata_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.MetadataPlugin
        )
        self.metadata_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        self.api_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.ApiPlugin,
            session=self.session_manager.session
        )
        self.api_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        self.validation_loader = plugin_loader.PluginLoader(
            plugin_class=_plugin_template.ValidationPlugin
        )
        self.validation_loader.import_plugins_from_directory(directory=self.booru_plugin_directory)

        destination = self.config["core"]["destination"]
        if destination:
            self.destination_plugin:_plugin_template.ApiPlugin = self.api_loader.load_matching_plugin(domain=destination, category=destination)
    
    async def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        """Finds the exact post from the destination site if present

        Args:
            post (resources.InternalPost): The post resource to use when searching

        Returns:
            resources.InternalPost | None: The exact post if found, otherwise None
        """
        logger.info(f"Getting exact post for '{post.id}'")

        if post.post_url not in post.sources:
            logger.debug(f"Adding post url '{post.post_url}' to sources for '{post.id}'")
            post.sources.append(post.post_url)

        exact_post = await self.destination_plugin.find_exact_post(post=post)
        return exact_post

    async def update_posts(self, posts:list[resources.InternalPost]) -> None:
        """Updates or creates the posts on the destination site

        Args:
            posts (list[resources.InternalPost]): The list of posts to update/create
        """
        logger.info(f"Updating {len(posts)} posts")
        found_tags = []
        post_update_concurrency = max(1, int(self.config["core"].get("post_update_concurrency", 2)))
        large_file_size_mb = max(1, int(self.config["core"].get("large_file_size_mb", 20)))
        large_file_size_bytes = large_file_size_mb * 1024 * 1024
        large_file_concurrency = max(1, int(self.config["core"].get("large_file_concurrency", 1)))
        recovery_successes = max(1, int(self.config["core"].get("transient_backoff_recovery_successes", 8)))

        logger.info(
            f"Using adaptive post update concurrency normal={post_update_concurrency}, "
            f"large={large_file_concurrency}, large_threshold={large_file_size_mb}MB"
        )

        prepared_posts:list[resources.InternalPost] = []
        for post in posts:
            post = self._prepare_post_for_push(post=post)
            if post.tags:
                found_tags.extend(post.tags)
            prepared_posts.append(post)

        state_lock = asyncio.Lock()
        state_updated = asyncio.Condition(lock=state_lock)
        active_jobs = 0
        active_large_jobs = 0
        current_limit = post_update_concurrency
        successes_since_backoff = 0

        async def _acquire_slot(is_large:bool) -> None:
            nonlocal active_jobs, active_large_jobs
            async with state_updated:
                while True:
                    no_large_jobs = active_large_jobs == 0
                    if is_large:
                        if no_large_jobs and active_jobs < large_file_concurrency:
                            active_jobs += 1
                            active_large_jobs += 1
                            return
                    else:
                        if no_large_jobs and active_jobs < current_limit:
                            active_jobs += 1
                            return
                    await state_updated.wait()

        async def _release_slot(is_large:bool) -> None:
            nonlocal active_jobs, active_large_jobs
            async with state_updated:
                active_jobs -= 1
                if is_large:
                    active_large_jobs -= 1
                state_updated.notify_all()

        async def _on_transient_failure(post:resources.InternalPost, reason:Any) -> None:
            nonlocal current_limit, successes_since_backoff
            async with state_updated:
                successes_since_backoff = 0
                if current_limit != large_file_concurrency:
                    logger.warning(
                        f"Detected transient upload failure while pushing '{post.id}' ({reason}), "
                        f"temporarily reducing post concurrency to {large_file_concurrency}"
                    )
                current_limit = large_file_concurrency
                state_updated.notify_all()

        async def _on_success() -> None:
            nonlocal current_limit, successes_since_backoff
            async with state_updated:
                if current_limit != large_file_concurrency:
                    return
                successes_since_backoff += 1
                if successes_since_backoff >= recovery_successes:
                    current_limit = post_update_concurrency
                    successes_since_backoff = 0
                    logger.info(
                        f"Recovered adaptive concurrency back to {post_update_concurrency} "
                        f"after {recovery_successes} successful pushes"
                    )
                    state_updated.notify_all()

        async def _push_single_post(post:resources.InternalPost) -> None:
            file_size = self._get_post_file_size(post=post)
            is_large = bool(file_size and file_size >= large_file_size_bytes)
            await _acquire_slot(is_large=is_large)
            try:
                logger.debug(f"Updating post '{post.id}'")
                result = await self.destination_plugin.push_post(post=post)
                if post.local_file and result is None:
                    await _on_transient_failure(post=post, reason="empty-result")
                else:
                    await _on_success()
            except (errors.GatewayTimeout, errors.ServiceUnavailable, errors.TooManyRequestsError, aiohttp.ClientError) as e:
                await _on_transient_failure(post=post, reason=type(e).__name__)
                raise
            finally:
                await _release_slot(is_large=is_large)

        async with asyncio.TaskGroup() as task_group:
            for post in prepared_posts:
                task_group.create_task(_push_single_post(post=post))
        
        filtered_tags = self.filter_tags(tags=found_tags)
        
        if not filtered_tags:
            logger.debug("No tags require potential updating")
            return None
        
        if not self.config["core"]["update_tag_categories"]:
            logger.info("Tag category updates disabled, skipping")
            return None
        
        logger.info(f"Updating tags for {len(filtered_tags)} tags")
        await self.update_tags(tags=filtered_tags)
        return None

    def _prepare_post_for_push(self, post:resources.InternalPost) -> resources.InternalPost:
        if not post.local_file:
            logger.debug(f"No file to upload for '{post.id}'")
        else:
            logger.debug(f"File '{post.local_file.name}' found for '{post.id}'")
            post = self.add_missing_post_hashes(post=post)

        if self.config["core"]["add_video_metatags"]:
            try:
                post = FFmpeg.add_video_tags(post=post)
            except Exception as e:
                logger.error(f"Error adding video tags to '{post.id}' with {e}")
                logger.trace(traceback.format_exc())

        if post.post_url and post.post_url not in post.sources:
            logger.debug(f"Updating post ({post.id}) sources with '{post.post_url}'")
            post.sources.append(post.post_url)

        destination_sources = [
            source for source in post.sources
            if self.destination_plugin.URL_BASE and self.destination_plugin.URL_BASE in source
        ]
        for source in destination_sources:
            logger.debug(
                f"Removing source '{source}' as its for the destination site '{self.destination_plugin.URL_BASE}'"
            )
            post.sources.pop(post.sources.index(source))

        return post

    @staticmethod
    def _get_post_file_size(post:resources.InternalPost) -> int:
        if not post.local_file:
            return 0
        if not post.local_file.exists():
            return 0
        try:
            return post.local_file.stat().st_size
        except OSError:
            return 0

    async def _expand_blacklist_tag(self, tag_name: str, visited: set) -> set:
        """Collect all aliases (names) for a single tag from the destination site.

        Fetches the tag and returns all of its known names so that any alias of a
        blacklisted tag is also treated as blacklisted. Implications are intentionally
        not followed — expanding those was too broad and excluded unrelated posts.

        Args:
            tag_name (str): The primary name of the tag to expand.
            visited (set): Names already looked up in this expansion (mutated in place).

        Returns:
            set: The tag name plus all of its aliases on the destination site.
        """
        if tag_name in visited:
            return set()
        visited.add(tag_name)
        result = {tag_name}

        try:
            found_tag = await self.destination_plugin.find_exact_tag(
                tag=resources.InternalTag(names=[tag_name])
            )
        except Exception as e:
            logger.debug(f"Could not fetch blacklist tag '{tag_name}' from destination: {e}")
            return result

        if not found_tag:
            return result

        result.update(found_tag.names)

        return result

    # ------------------------------------------------------------------
    # Blacklist disk cache helpers
    # ------------------------------------------------------------------

    def _blacklist_cache_hash(self, base_blacklist: list) -> str:
        """Return a stable hex digest of the raw blacklist + destination name.
        Any change to the list or the destination invalidates the cached file."""
        payload = json.dumps(
            {"destination": self.config["core"].get("destination", ""), "blacklist": base_blacklist},
            sort_keys=True,
            default=str
        )
        return hashlib.md5(payload.encode()).hexdigest()

    def _load_blacklist_cache(self, base_blacklist: list) -> tuple | None:
        """Try to load a valid expanded blacklist from disk.

        Returns ``(expanded_blacklist, tag_aliases)`` if the file exists, is within
        the configured TTL, and was generated from the same raw blacklist + destination.
        Returns ``None`` on any miss or error.
        """
        ttl_hours = int(self.config["core"].get("blacklist_cache_ttl_hours", 24))
        if ttl_hours <= 0:
            return None

        cache_file = Path(self.config["core"].get("blacklist_cache_file", "blacklist_cache.json"))

        if not cache_file.exists():
            logger.debug(f"Blacklist cache file '{cache_file}' not found")
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            created_at = datetime.fromisoformat(data["created_at"])
            expiry = created_at + timedelta(hours=ttl_hours)
            now = datetime.now(tz=timezone.utc)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)

            if now > expiry:
                logger.debug(
                    f"Blacklist cache expired (created {created_at.isoformat()}, "
                    f"TTL {ttl_hours}h, expired {expiry.isoformat()})"
                )
                return None

            expected_hash = self._blacklist_cache_hash(base_blacklist)
            if data.get("base_blacklist_hash") != expected_hash:
                logger.debug("Blacklist cache hash mismatch — raw blacklist or destination changed")
                return None

            expanded = data["expanded_blacklist"]
            tag_aliases = data.get("tag_aliases", {})
            logger.info(
                f"Loaded {len(expanded)} expanded blacklist entries from disk cache "
                f"'{cache_file}' (expires {expiry.isoformat()})"
            )
            return expanded, tag_aliases

        except Exception as e:
            logger.warning(f"Could not read blacklist cache from '{cache_file}': {e}")
            return None

    def _save_blacklist_cache(self, base_blacklist: list, expanded: list, tag_aliases: dict) -> None:
        """Persist the expanded blacklist and per-tag alias map to disk."""
        ttl_hours = int(self.config["core"].get("blacklist_cache_ttl_hours", 24))
        if ttl_hours <= 0:
            return

        cache_file = Path(self.config["core"].get("blacklist_cache_file", ".cache/blacklist_cache.json"))

        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "base_blacklist_hash": self._blacklist_cache_hash(base_blacklist),
                "base_blacklist": base_blacklist,
                "tag_aliases": tag_aliases,
                "expanded_blacklist": expanded,
            }
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            logger.debug(f"Blacklist cache saved to '{cache_file}' (TTL {ttl_hours}h)")
        except Exception as e:
            logger.warning(f"Could not save blacklist cache to '{cache_file}': {e}")

    async def expand_blacklist_tags(self) -> None:
        """Pre-populate the expanded blacklist from the destination site.

        For every tag name that appears in the configured blacklist (including
        individual tags inside AND conditions), this fetches the tag from the
        destination plugin and collects all of its known aliases (names).

        Simple OR entries are flattened into individual alias strings in
        ``_expanded_blacklist`` so standard set-membership checking works.
        AND entries (e.g. ``1futa|solo`` from YAML, or ``["1futa","solo"]`` from CLI)
        are kept as sublists of the *original* tag names; at check time the
        ``_tag_aliases`` dict resolves each name to its full alias set so that any
        alias of every required tag triggers the AND match.

        A disk cache (JSON) avoids re-querying the destination on every run.
        It is invalidated when the TTL expires, the raw blacklist changes, or the
        destination changes.  Set ``blacklist_cache_ttl_hours`` to ``0`` to disable.

        Results are stored in ``self._expanded_blacklist`` / ``self._tag_aliases``
        and reused on subsequent calls (idempotent — no-op if already populated).
        """
        if self._expanded_blacklist is not None:
            return

        if not hasattr(self, "destination_plugin"):
            logger.debug("No destination plugin available; skipping blacklist expansion")
            self._expanded_blacklist = self.config["core"]["blacklisted_tags"]
            self._tag_aliases = {}
            return

        base_blacklist = self.config["core"]["blacklisted_tags"]
        if not base_blacklist:
            self._expanded_blacklist = []
            self._tag_aliases = {}
            return

        # Try disk cache first
        cached = self._load_blacklist_cache(base_blacklist)
        if cached is not None:
            self._expanded_blacklist, self._tag_aliases = cached
            return

        # Normalise entries: YAML stores "1futa|solo" as a plain string; split these
        # into AND sublists so they are never sent to the API as a compound name.
        normalized: list = []
        for entry in base_blacklist:
            if isinstance(entry, str) and "|" in entry:
                normalized.append(entry.split("|"))
            else:
                normalized.append(entry)

        # Collect every unique individual tag name we need to look up
        individual_tags: set[str] = set()
        for entry in normalized:
            if isinstance(entry, str):
                individual_tags.add(entry)
            else:
                individual_tags.update(entry)

        # Expand each individual tag to its full alias set (one API call per tag)
        tag_aliases: dict[str, list[str]] = {}
        for tag_name in sorted(individual_tags):
            aliases = await self._expand_blacklist_tag(tag_name, visited=set())
            tag_aliases[tag_name] = sorted(aliases)

        # Build the expanded blacklist:
        #   - Simple OR strings  → add each alias as its own OR entry
        #   - AND sublists       → keep the sublist of original names (resolved via
        #                          tag_aliases at check time, no combinatorial explosion)
        expanded: list = []
        seen_strings: set = set()

        for entry in normalized:
            if isinstance(entry, str):
                for alias in tag_aliases.get(entry, [entry]):
                    if alias not in seen_strings:
                        expanded.append(alias)
                        seen_strings.add(alias)
            else:
                expanded.append(entry)

        self._expanded_blacklist = expanded
        self._tag_aliases = tag_aliases
        logger.info(
            f"Blacklist expanded: {len(base_blacklist)} raw entries → "
            f"{len(expanded)} OR entries + "
            f"{sum(1 for e in expanded if isinstance(e, list))} AND conditions, "
            f"{len(tag_aliases)} individual tags aliased"
        )

        self._save_blacklist_cache(base_blacklist, expanded, tag_aliases)

    def check_post_allowed(self, post:resources.InternalPost) -> bool:
        """Check if the provided post resource meets the requirements to be uploaded

        Args:
            post (resources.InternalPost): The post resource to check if allowed

        Returns:
            bool: Whether the post is allowed to be uploaded
        """
        if self._expanded_blacklist is not None and self._tag_aliases is not None:
            post_tags = set(post.str_tags)
            for entry in self._expanded_blacklist:
                if isinstance(entry, str):
                    if entry in post_tags:
                        logger.debug(f"Post '{post.id}' contains blacklisted tag '{entry}'")
                        return False
                elif isinstance(entry, list):
                    # AND condition: every component must be represented by at least
                    # one of its aliases in the post's tag set
                    all_present = all(
                        any(alias in post_tags for alias in self._tag_aliases.get(tag, [tag]))
                        for tag in entry
                    )
                    if all_present:
                        logger.debug(
                            f"Post '{post.id}' matches blacklisted AND condition {entry}"
                        )
                        return False
        else:
            # Fallback before expansion has run
            blacklisted_tags = self.config["core"]["blacklisted_tags"]
            if post.contains_any_tags(tags=blacklisted_tags):
                logger.debug(f"Post '{post.id}' contains blacklisted tags from {blacklisted_tags}")
                return False
        required_tags = self.config["core"]["required_tags"]
        if not post.contains_all_tags(tags=required_tags):
            logger.debug(f"Post '{post.id}' does not contain all required tags from {required_tags}")
            return False
        allowed_safety = self.config["core"]["allowed_safety"]
        if allowed_safety and (post.safety not in allowed_safety):
            logger.debug(f"Post '{post.id}' with '{post.safety}' is not in the allowed safety selection from {allowed_safety}")
            return False
        minimum_score = self.config["core"]["minimum_score"]
        if minimum_score and post.score < minimum_score:
            logger.debug(f"Post '{post.id}' has a score of {post.score} which is below the minimum score of {minimum_score}")
            return False
        if post.deleted:
            logger.debug(f"Post '{post.id}' is marked as deleted")
            return False
        logger.debug(f"Post '{post.id}' passed all checks")
        return True

    async def update_tags(self, tags:list[resources.InternalTag]):
        """The tags to push to the destination site

        Args:
            tags (list[resources.InternalTag]): The list of tags to push to the destination site
        """
        logger.info(f"Updating {len(tags)} tags")
        for tags_chunk in self.divide_chunks(tags, max_size=500):
            tasks:list[asyncio.Task] = []
            async with asyncio.TaskGroup() as task_group:
                for tag in tags_chunk:
                    task = task_group.create_task(
                        self.destination_plugin.push_tag(tag=tag)
                    )
                    tasks.append(task)
            results = [task.result() for task in tasks]
    
    def cleanup_process_directories(self) -> None:
        """Cleans up the temporary directories
        """
        directories_to_delete:list[Path] = [
            self.tmp_directory
        ]

        if not self.cleanup_temp_directories:
            logger.debug("Skipping cleanup of temporary directories as its disabled")
            return None

        for directory in directories_to_delete:
            self.delete_directory(directory=directory)

        return None
    
    def delete_directory(self, directory:Path) -> None:
        """Deletes the provided directory

        Args:
            directory (Path): The directory to delete
        """
        logger.debug(f"Deleting '{directory}' folder")
        if not Path(directory).exists():
            logger.debug(f"Directory '{directory}' does not exist, skipping deletion")
            return
        shutil.rmtree(directory)
    
    def add_missing_post_hashes(self, post:resources.InternalPost) -> resources.InternalPost:
        """Add missing or mismatched hashes to post resource

        Args:
            post (resources.InternalPost): The post resource to update file hashes for

        Returns:
            resources.InternalPost: The post resource with updated hashes
        """
        file_md5 = self.get_md5_hash(file_path=post.local_file)
        file_sha1 = self.get_sha1_hash(file_path=post.local_file)

        if post.md5 != file_md5:
            if post.md5:
                logger.warning(f"Post '{post.id}' md5 hash '{post.md5}' is different from file md5 hash '{file_md5}'")
            logger.debug(f"Updating post '{post.id}' md5 hash from '{post.md5}' to '{file_md5}'")
            post.md5 = file_md5
        if post.sha1 != file_sha1:
            if post.sha1:
                logger.warning(f"Post '{post.id}' sha1 hash '{post.sha1}' is different from file sha1 hash '{file_sha1}'")
            logger.debug(f"Updating post '{post.id}' sha1 hash from '{post.sha1}' to '{file_sha1}'")
            post.sha1 = file_sha1
        
        return post

    @staticmethod
    def get_md5_hash(file_path:Path) -> str:
        """Get the MD5 hash for the provided file

        Args:
            file_path (Path): The file to generate a MD5 hash for

        Returns:
            str: The MD5 hash for the file
        """
        if not file_path.exists():
            return ""
        
        logger.debug(f"Calculating md5 hash for '{file_path}'")
        with open(file_path, "rb") as file:
            file_hash = hashlib.md5()
            while chunk := file.read(8192):
                file_hash.update(chunk)

        md5_hash = file_hash.hexdigest()
        logger.debug(f"MD5 hash for '{file_path}' is '{md5_hash}'")
        return md5_hash

    @staticmethod
    def get_sha1_hash(file_path:Path) -> str:
        """Get the SHA1 hash for the provided file

        Args:
            file_path (Path): The file to generate a SHA1 hash for

        Returns:
            str: The SHA1 hash for the file
        """
        if not file_path.exists():
            return ""
        
        logger.debug(f"Calculating sha1 hash for '{file_path}'")
        with open(file_path, "rb") as file:
            file_hash = hashlib.sha1()
            while chunk := file.read(8192):
                file_hash.update(chunk)

        sha1_hash = file_hash.hexdigest()
        logger.debug(f"SHA1 hash for '{file_path}' is '{sha1_hash}'")
        return sha1_hash

    @staticmethod
    def split_tag_list(tag_string:str, and_seperator:str="|", or_seperator:str=",") -> list[str|list[str]]:
        """Split a tag string into a list of tags for more complex tag matching`

        Args:
            tag_string (str): The tag string to split into a list
            and_seperator (str, optional): The and seperator for any split strings, creating a sublist. Defaults to "|".
            or_seperator (str, optional): The or seperate to seperate the string with. Defaults to ",".

        Returns:
            list[str|list[str]]: The list of tag strings for more complex tag matching
        """
        tags = []
        comma_split_tags = [tag for tag in tag_string.split(or_seperator) if tag != ""]
        for tag in comma_split_tags:
            if and_seperator in tag:
                and_tags = tag.split(and_seperator)
                tags.append(and_tags)
            else:
                tags.append(tag)
        return tags
    
    @staticmethod
    def divide_chunks(array:list, max_size:int=50) -> Generator[list, None, None]:
        """Divide the provided array into chunks of the provided size through a generator

        Args:
            array (list): The array to divide into chunks
            max_size (int, optional): The max chunk size to split by. Defaults to 50.

        Yields:
            list: The divided chunks of the array
        """
        total_size = len(array)
        for i in range(0, len(array), max_size):
            new_max = i + max_size
            chunk = array[i:new_max]

            chunk_size = len(chunk)
            completion_percent = int((new_max / total_size) * 100)
            if completion_percent > 100:
                completion_percent = 100
            logger.info(f"Creating chunk {i}-{new_max} ({chunk_size} of {total_size} total items) - {completion_percent}% complete")

            yield chunk
    
    def override_plugin_config(self, plugin:object, plugin_override:str=""):
        override_pairs = plugin_override.split(",")
        for pair in override_pairs:
            key, value = pair.split("=")
            setattr(plugin, key, value)

    @staticmethod
    def filter_tags(tags:list[resources.InternalTag]) -> list[resources.InternalTag]:
        """Filter out tags that are in the default/invalid category

        Args:
            tags (list[resources.InternalTag]): The list of tags to filter

        Returns:
            list[resources.InternalTag]: The list of filtered tags
        """
        filtered_tags = []
        for tag in tags:
            if tag in filtered_tags:
                continue
            if tag.category.lower() in [constants.TagCategory._DEFAULT, constants.TagCategory.INVALID]:
                continue
            filtered_tags.append(tag)
        logger.debug(f"Filtered out tags in default category, going from {len(tags)} tags to {len(filtered_tags)} tags")
        return filtered_tags