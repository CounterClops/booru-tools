from loguru import logger
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from async_lru import alru_cache
import gzip, csv
import aiohttp
import re
import functools
import requests

from booru_tools.plugins import _plugin_template
from booru_tools.shared import errors, constants, resources

class SharedAttributes:
    _DOMAINS = [
        "e621.net"
    ]
    _CATEGORY = [
        "e621"
    ]
    _NAME = "e621"

    POST_CATEGORY_MAP = {
        "0": constants.Category.GENERAL,
        "1": constants.Category.ARTIST,
        "2": constants.Category.CONTRIBUTOR,
        "3": constants.Category.COPYRIGHT,
        "4": constants.Category.CHARACTER,
        "5": constants.Category.SPECIES,
        "6": constants.Category.INVALID,
        "7": constants.Category.META,
        "8": constants.Category.LORE
    }

    POST_SAFETY_MAPPING = {
        "safe": constants.Safety.SAFE,
        "s": constants.Safety.SAFE,
        "questionable": constants.Safety.SKETCHY,
        "q": constants.Safety.SKETCHY,
        "explicit": constants.Safety.UNSAFE,
        "e": constants.Safety.UNSAFE
    }
    URL_BASE = "https://e621.net"
    
    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/posts?tags="

class E621Meta(SharedAttributes, _plugin_template.MetadataPlugin):
    def get_id(self, metadata:dict) -> int:
        id:int = metadata["id"]
        return id

    def get_sources(self, metadata:dict) -> list[str]:
        sources = metadata.get("sources", [])
        return sources

    def get_description(self, metadata:dict) -> str:
        description:str = metadata.get("description", "")
        return description

    def get_score(self, metadata:dict) -> int:
        score:dict[str, int] = metadata.get("score", {})
        total_score:int = score.get("total", 0)
        return total_score

    def get_tags(self, metadata: dict) -> list[resources.InternalTag]:
        all_tags:list[resources.InternalTag] = []

        for category, tags in metadata.get("tags", {}).items():
            for tag in tags:
                tag = resources.InternalTag(
                    names=[tag],
                    category=category
                )
                all_tags.append(tag)
        
        logger.debug(f"Found {len(all_tags)} tags")
        return all_tags

    def get_created_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["created_at"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_updated_at(self, metadata:dict) -> datetime:
        datetime_str:str = metadata["updated_at"]
        datetime_obj:datetime = datetime.fromisoformat(datetime_str)
        return datetime_obj

    def get_relations(self, metadata:dict) -> resources.InternalRelationship:
        post_relationships:dict = metadata["relationships"]
        parent_id:int = post_relationships.get("parent_id", None)
        children:dict = post_relationships.get("children", None)

        relationships = resources.InternalRelationship(
            parent_id=parent_id,
            children=children
        )

        return relationships

    def get_safety(self, metadata:dict) -> str:
        rating:str = metadata["rating"]
        safety:str = self.POST_SAFETY_MAPPING.get(rating, constants.Safety._DEFAULT)
        return safety

    def get_md5(self, metadata: dict) -> str:
        metadata_file = metadata.get("file", {})
        try:
            md5 = metadata_file["md5"]
        except KeyError:
            raise errors.MissingMd5
        
        logger.debug(f"Found '{md5}' md5")
        return md5

    def get_post_url(self, metadata:dict) -> str:
        post_id = metadata["id"]
        url = f"{self.URL_BASE}/posts/{post_id}"
        logger.debug(f"Generated the post URL '{url}'")
        return url

    def get_pools(self, metadata:dict) -> list[resources.InternalPool]:
        post_pools:list[int] = metadata.get("pools", [])
        pools:list[resources.InternalPool] = []

        for pool_id in post_pools:
            pools.append(resources.InternalPool(
                id=pool_id
            ))
        
        return pools

class E621Client(SharedAttributes, _plugin_template.ApiPlugin):
    def __init__(self, session: aiohttp.ClientSession = None) -> None:
        self.session = session
        logger.debug(f"Loaded {self.__class__.__name__}")
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "booru-tools/1.0"
        }
        self.tag_post_count_threshold = 5
        self.tmp_path = Path("tmp")

    async def get_pool(self, id:int) -> resources.InternalPool:
        url = f"{self.URL_BASE}/pools.json?search[id]={id}"

        response = requests.get(
            url=url,
            headers=self.headers
        )

        pools = response.json()

        try:
            pool_data = pools[0]
            pool = resources.InternalPool(
                id=pool_data["id"],
                title=pool_data["name"],
                category=pool_data.get("category"),
                description=pool_data.get("description"),
                posts=pool_data["post_ids"]
            )
        except KeyError:
            pool = None

        return pool

    async def get_all_tags(self, treat_aliases_as_implications:bool=False) -> list[resources.InternalTag]:
        tag_aliases_export_archive = await self._download_latest_db_export(filename_string="tag_aliases-")
        tag_implications_export_archive = await self._download_latest_db_export(filename_string="tag_implications-")
        tags_export_archive = await self._download_latest_db_export(filename_string="tags-")

        tags:dict[str, resources.InternalTag] = {}

        with gzip.open(tags_export_archive, "rt") as tags_gz:
            logger.info(f"Processing tags from {tags_export_archive}")
            tags_csv_reader = csv.DictReader(tags_gz)

            for tag in tags_csv_reader:
                name = tag["name"]
                category_id = tag["category"]
                post_count = int(tag.get("post_count", 0))

                if post_count < self.tag_post_count_threshold:
                    # logger.debug(f"Skipping tag '{name}' as its under the post_count threshold of {self.tag_post_count_threshold}")
                    continue

                category = self.POST_CATEGORY_MAP.get(category_id, constants.Category._DEFAULT)

                if category == constants.Category.INVALID:
                    # logger.debug(f"Skipping tag '{name}' as its in the {constants.Category.INVALID} category")
                    continue
                
                tags[name] = resources.InternalTag(
                    names=[name],
                    category=category
                )
                # logger.debug(f"Added tag {name}")

        with gzip.open(tag_aliases_export_archive, "rt") as tag_aliases_gz:
            logger.info(f"Processing tag aliases from {tags_export_archive}")
            tag_aliases_csv_reader = csv.DictReader(tag_aliases_gz)

            for tag_alias in tag_aliases_csv_reader:
                if tag_alias.get("status", "deleted") != "active":
                    continue
                name = tag_alias["consequent_name"]
                alias = tag_alias["antecedent_name"]
                if treat_aliases_as_implications:
                    tags = self._add_implication(
                        tags=tags,
                        name=name,
                        implication=alias
                    )
                else:
                    tags = self._add_alias(
                        tags=tags,
                        name=name,
                        alias=alias
                    )
            
        with gzip.open(tag_implications_export_archive, "rt") as tag_implications_gz:
            logger.info(f"Processing tag implications from {tags_export_archive}")
            tag_implications_csv_reader = csv.DictReader(tag_implications_gz)

            for tag_implication in tag_implications_csv_reader:
                if tag_implication.get("status", "deleted") != "active":
                    continue
                name = tag_implication["antecedent_name"]
                implication = tag_implication["consequent_name"]

                tags = self._add_implication(
                    tags=tags,
                    name=name,
                    implication=implication
                )
            
        return tags.values()
    
    async def get_all_pools(self) -> list[resources.InternalPool]:
        pools_export_archive = await self._download_latest_db_export(filename_string="pools-")

        pools:list[resources.InternalPool] = []

        with gzip.open(pools_export_archive, "rt") as pools_gz:
            pools_csv_reader = csv.DictReader(pools_gz)

            for pool in pools_csv_reader:
                if pool.get("is_active", "f") != "t":
                    continue
                
                pool_data = {
                    "id": int(pool["id"]),
                    "name": pool["name"],
                    "created_at": datetime.fromisoformat(pool["created_at"]),
                    "updated_at": datetime.fromisoformat(pool["updated_at"]),
                    "description": pool["description"],
                    "category": pool["category"]
                }

                post_ids:list[str] = pool["post_ids"].strip("{}").split(",")
                pool_data["posts"] = [{"id": post_id} for post_id in post_ids]

                pools.append(resources.InternalPool.from_dict(pool_data))
            
        return pools
    
    async def get_all_posts(self) -> list[resources.InternalPost]:
        posts_export_archive = await self._download_latest_db_export(filename_string="posts-")

        posts:list[resources.InternalPost] = []

        with gzip.open(posts_export_archive, "rt") as posts_gz:
            posts_csv_reader = csv.DictReader(posts_gz)
            
            for post in posts_csv_reader:

                if post.get("is_deleted", "t") != "f":
                    continue
                if post.get("is_pending", "t") != "f":
                    continue
                if post.get("is_flagged", "t") != "f":
                    continue

                post_data = {
                    "id": int(post["id"]),
                    "created_at": datetime.fromisoformat(post["created_at"]),
                    "updated_at": datetime.fromisoformat(post["updated_at"]),
                    "md5": post["md5"],
                    "source": post["source"].split("\n"),
                    "rating": self.POST_SAFETY_MAPPING.get(post["rating"], "sketchy"),
                    "tags": [{"names": [tag]} for tag in post["tag_string"].split(" ")],
                    "description": post["description"]
                } 

                posts.append(resources.InternalPost.from_dict(post_data))
        
        return posts
    
    async def _download_latest_db_export(self, filename_string:str) -> Path|None:
        db_export_links = await self._get_db_export_links()
        db_export_links.sort(key=lambda link: link.split("/")[-1], reverse=True)
        
        for link in db_export_links:
            filename = link.split("/")[-1]
            if filename_string not in filename:
                continue

            async with self.session.get(
                url=link
                ) as response:
                content = await response.content.read()
            
            local_file = self.create_tmp_directory() / filename
            with open(local_file, "wb") as file:
                file.write(content)

            logger.debug(f"Downloaded db export '{filename}'")

            return local_file
        return None

    @alru_cache(ttl=120)
    async def _get_db_export_links(self) -> list[str]:
        url = f"{self.URL_BASE}/db_export/"
        export_file_extension = ".csv.gz"
        
        async with self.session.get(
            url=url
            ) as response:
            content = await response.content.read()

        soup = BeautifulSoup(content, "html.parser")
        links = soup.find_all("a", href=True)
        file_links = [url + link["href"] for link in links if link["href"].endswith(export_file_extension)]

        return file_links

    def _add_implication(self, tags:dict[str, resources.InternalTag], name:str, implication:str):

        if implication in tags[name].names:
            logger.warning(f"Skipping implication '{implication}' as it already exists in names/aliases of '{name}'")
            return tags

        logger.debug(f"Adding implication '{implication}' to '{name}'")
        try:
            tags[name].implications.append(tags[implication])
        except KeyError:
            logger.debug(f"Skipping implication '{implication}' as the tag '{name}' or '{implication}' didn't exist")
        return tags

    def _add_alias(self, tags:dict[str, resources.InternalTag], name:str, alias:str):
        logger.debug(f"Adding alias '{alias}' to '{name}'")
        try:
            tags[name].names.append(alias)
        except KeyError:
            logger.debug(f"Skipping alias '{alias}' as the tag '{name}' didn't exist")
        return tags

class E621Validator(SharedAttributes, _plugin_template.ValidationPlugin):
    POST_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/posts\/.+)|(https:\/\/[a-zA-Z0-9.-]+\/data\/sample\/.+)")
    GLOBAL_URL_PATTERN = re.compile(r"(https:\/\/[a-zA-Z0-9.-]+\/?$)")
    
    def get_source_type(self, url:str):
        if self.POST_URL_PATTERN.match(url):
            return constants.SourceTypes.POST
        if self.GLOBAL_URL_PATTERN.match(url):
            return constants.SourceTypes.GLOBAL
        return constants.SourceTypes._DEFAULT