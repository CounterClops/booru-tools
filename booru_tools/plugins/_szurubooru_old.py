from dataclasses import dataclass, field
import requests

from pathlib import Path
import urllib.parse
from booru_tools.plugins import _template
from booru_tools.shared import resources
from booru_tools.shared import errors
from loguru import logger

@dataclass(kw_only=True)
class PagedSearch:
    offset: int
    limit: int
    total: int
    query: str = ""
    results: list = field(default_factory=list)

    def __str__(self) -> str:
        resource_string = f"query={self.query}, offset={self.offset}, limit={self.limit}, total={self.total}, results_count={len(self.results)}"
        return resource_string

class SzurubooruMeta(_template.MetadataPlugin):
    _DOMAINS = []
    _CATEGORY = [
        "szurubooru"
    ]
    _NAME = "szurubooru"

    def __init__(self, config:dict={}):
        self.url_base = "" # Update this to pull from config
        self.import_config(config=config)

    def get_post_url(self, metadata:dict) -> str:
        post_id = metadata['id']
        url = f"{self.url_base}/post/{post_id}"
        logger.debug(f"Generated the post URL '{url}'")
        return url
    
    def get_safety(self, metadata: dict) -> str:
        safety = metadata.get("rating", "safe")
        return safety

class SzurubooruClient(_template.ApiPlugin):
    _DOMAINS = []
    _CATEGORY = [
        "szurubooru"
    ]
    _NAME = "szurubooru"

    def __init__(self, config:dict={}) -> None:
        self.image_distance_threshold = 0.15
        self.import_config(config=config)
        logger.debug(f'username = {self.username}')
        logger.debug(f'url_base = {self.url_base}')

        self.szurubooru_api_url = self.url_base + '/api'
        logger.debug(f'szurubooru_api_url = {self.szurubooru_api_url}')

        token = self.encode_auth_headers(self.username, self.password)
        self.headers = {'Accept': 'application/json', 'Authorization': f'Token {token}'}

    def post_search(self, search_query:str, search_size:int=100, offset:int=0) -> list:
        url = f"{self.szurubooru_api_url}/posts/"
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        response = requests.get(
            url=url,
            headers=self.headers,
            params=params
        )

        search = PagedSearch(
            **response.json()
        )
        posts = search.results

        return posts

    def post_md5_search(self, md5_hash:str, search_size:int=1) -> dict:
        search_query = f"md5:{md5_hash}"
        posts = self.post_search(
            search_query=search_query,
            search_size=search_size
        )
        return posts

    def check_md5_post_exists(self, md5_hash:str) -> int:
        posts = self.post_md5_search(md5_hash=md5_hash, search_size=1)
        if posts:
            post_id = posts[0]['id']
            return post_id
        return None
    
    def check_sources_post_exists(self, sources:list) -> int:
        for source in sources:
            search_query = f"source:{source}"
            posts = self.post_search(
                search_query=search_query,
                search_size=1
            )
            if posts:
                post_id = posts[0]['id']
                return post_id
        return None
    
    def pool_search(self, search_query:str, search_size:int=100, offset:int=0) -> list:
        url = f"{self.szurubooru_api_url}/pools/"
        
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        response = requests.get(
            url=url,
            headers=self.headers,
            params=params
        )

        search = PagedSearch(
            **response.json()
        )

        pools = search.results
        
        return pools
    
    def upload_temporary_file(self, file:Path) -> str:
        """Upload the provided file to the Szurubooru temporary upload endpoint

        Args:
            file (Path): The file to be uploaded

        Returns:
            token (str): The content token to be used for referencing the temporary file
        """
        url = f"{self.szurubooru_api_url}/uploads"

        with open(file, 'rb') as file_content:
            files = {'content': (file.name, file_content)}
            response = requests.post(
                url=url, 
                files=files,
                headers=self.headers
            )

        token = response.json()["token"]
        
        logger.debug(f"Uploaded file to temporary endpoint with token={token}")
        return token

    def create_post(self, content_token:str, post:resources.InternalPost) -> dict:
        url = f"{self.szurubooru_api_url}/posts/"

        data = {
            "tags": post.tags,
            "safety": post.safety,
            "source": post.source,
            "contentToken": content_token
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        post = response.json()

        return post

    def reverse_image_search(self, content_token:str):
        logger.debug("Doing reverse image search")
        url = f"{self.szurubooru_api_url}/posts/reverse-search"

        data = {
            "contentToken": content_token
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        image_search = response.json()

        return image_search

    def push_post(self, file:Path, post:resources.InternalPost):
        content_token = self.upload_temporary_file(file=file)
        reverse_image_search = self.reverse_image_search(content_token=content_token)
        
        exact_post = reverse_image_search.get("exactPost", None)

        if exact_post:
            logger.info("Exact post already exists, skipping post creation")
            return
        
        similar_posts = reverse_image_search.get("similarPosts", [])

        if similar_posts:
            closest_posts = [post for post in similar_posts if post["distance"] < self.image_distance_threshold]
            sorted_posts = sorted(closest_posts, key=lambda x: x["distance"])
            if sorted_posts:
                min_distance = sorted_posts[0].get("distance", "NA")
                max_distance = sorted_posts[-1].get("distance", "NA")
                logger.info(f"Similar posts already exists {len(sorted_posts)} with a range of {min_distance}-{max_distance}, skipping post creation")
                return

        post = self.create_post(
            content_token=content_token, 
            post=post
        )
    
    def search_tags(self, search_query:str, search_size:int=100, offset:int=0):
        url = f"{self.szurubooru_api_url}/tags/"
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        response = requests.get(
            url=url,
            headers=self.headers,
            params=params
        )

        tag_search = PagedSearch(
            **response.json()
        )

        tags = tag_search.results

        return tags

    def get_tag(self, tag:str, search_size:int=100, offset:int=0):
        safe_tag = urllib.parse.quote(tag)
        url = f"{self.szurubooru_api_url}/tag/{safe_tag}"

        response = requests.get(
            url=url,
            headers=self.headers
        )

        tag = response.json()

        return tag

    # def list_all_tags(self) -> list[Tag]:
    #     all_tags = []
    #     offset = 0
    #     limit = 100

    #     while tags > 0:
    #         tags = self.search_tags(
    #             search_query="", 
    #             offset=offset, 
    #             limit=100
    #         )
    #         offset += limit

    #         for tag in tags:
    #             all_tags.append(
    #                 Tag(
    #                     version=tag["version"],
    #                     names=tag["names"],
    #                     category=tag["category"]
    #                 )
    #             )

    #     return all_tags

    def create_tag(self, tag:str, tag_category:str="") -> dict:
        url = f"{self.szurubooru_api_url}/tags"

        data = {
            "names": [tag],
            "category": tag_category
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        tag = response.json()

        return tag

    def update_tag(self, version_id:int, tag:str, tag_category:str="") -> dict:
        url = f"{self.szurubooru_api_url}/tag/{tag}"

        data = {
            "version": version_id,
            "category": tag_category
        }

        response = requests.put(
            url=url,
            json=data,
            headers=self.headers
        )

        tag = response.json()

        return tag
    
    def push_tag(self, tag:str, tag_category:str="") -> dict:
        original_tag = self.get_tag(tag=tag)

        tag_category_matches = original_tag.get("category", "") == tag_category

        if tag_category_matches:
            logger.debug(f"Skipping update on tag '{tag}' as it already matches")
            return original_tag
        
        if original_tag:
            updated_tag = self.update_tag(
                version_id=original_tag["version"],
                tag=tag,
                tag_category=tag_category
            )
        else:
            updated_tag = self.create_tag(
                tag=tag,
                tag_category=tag_category
            )

        return updated_tag

    def pool_search(self, search_query:str, search_size:int=100, offset:int=0) -> list:
        url = f"{self.szurubooru_api_url}/pools/"
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        response = requests.get(
            url=url,
            headers=self.headers,
            params=params
        )

        try:
            search = PagedSearch(
                **response.json()
            )
        except Exception as e:
            print(e)
            print(response.json())
            exit()

        pools = search.results
        
        return pools

    def create_pool(self, name:str, category:str, description:str, posts:list):
        logger.debug(f"Creating pool '{name}' with {len(posts)}")
        url = f"{self.szurubooru_api_url}/pool"
        data = {
            "names": [name],
            "category": category,
            "description": description,
            "posts": posts
        }

        response = requests.post(
            url=url,
            headers=self.headers,
            json=data
        )

        pool = response.json()
        
        return pool

    def update_pool(self, id:int, version:int, name:str, category:str, description:str, posts:list):
        logger.debug(f"Updating pool '{name}' with {len(posts)}")
        url = f"{self.szurubooru_api_url}/pool/{id}"
        data = {
            "version": version,
            "names": name,
            "category": category,
            "description": description,
            "posts": posts
        }

        response = requests.put(
            url=url,
            headers=self.headers,
            json=data
        )

        pool = response.json()
        
        return pool

    def escape_string(self, string) -> str:
        characters_to_escape = ['\\', '*', ':', '-', '.']
            
        escaped_string = ""
        for char in string:
            if char in characters_to_escape:
                escaped_string += '\\' + char  # Prepend backslash
            else:
                escaped_string += char  # Leave unchanged
        
        return escaped_string

    def push_pool(self, pool:resources.InternalPool):
        """Create/update the provided pool

        Args:
            pool (resources.InternalPool): The pool data to use for the update or creation

        Returns:
            _type_: The returned pool data
        """
        search_query = f"name:{self.escape_string(pool.title)}"
        logger.debug(f"Checking for pool '{pool.title}' with search '{search_query}'")
        pools = self.pool_search(search_query=search_query)
        existing_pool = next((possible_pool for possible_pool in pools if pool.title in possible_pool['names']), None)

        post_list = pool.posts

        if existing_pool:
            updated_pool = self.update_pool(
                id=existing_pool["id"],
                version=existing_pool["version"],
                name=pool.title,
                category=pool.category,
                description=pool.description,
                posts=post_list
            )
        else:
            updated_pool = self.create_pool(
                name=pool.title,
                category=pool.category,  
                description=pool.description,
                posts=post_list
            )
        
        return updated_pool
