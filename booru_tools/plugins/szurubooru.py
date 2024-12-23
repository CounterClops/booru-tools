from dataclasses import dataclass, field, fields
import requests

from typing import Optional, Literal, Type, Generic, TypeVar
from pathlib import Path
import urllib.parse
from datetime import datetime
from booru_tools.plugins import _plugin_template
from booru_tools.shared import resources, errors, constants
from loguru import logger

@dataclass(kw_only=True)
class SzurubooruResource:
    @classmethod
    def from_dict(cls, data:dict):
        return cls(**data)
    
    @classmethod
    def filter_valid_keys(cls, data:dict):
        valid_keys = {field.name for field in fields(cls)}
        filtered_data = {key: value for key, value in data.items() if key in valid_keys}
        return filtered_data

    def to_resource(self) -> resources.InternalResource:
        raise NotImplementedError

@dataclass(kw_only=True)
class MicroUser(SzurubooruResource):
    name: str
    avatarUrl: str

@dataclass(kw_only=True)
class MicroTag(SzurubooruResource):
    names: list[str]
    category: str
    usages: int = 0

    def to_resource(self) -> resources.InternalTag:
        kwargs = {}

        if self.names:
            kwargs["names"] = self.names
        if self.category:
            kwargs["category"] = self.category

        return resources.InternalTag(**kwargs)

@dataclass(kw_only=True)
class MicroPost(SzurubooruResource):
    id: int
    thumbnailUrl: str = ""

    def to_resource(self) -> resources.InternalPost:
        kwargs = {}

        if self.id:
            kwargs["id"] = self.id
        kwargs["category"] = "szurubooru"

        return resources.InternalPost(**kwargs)

@dataclass(kw_only=True)
class MicroPool(SzurubooruResource):
    id: int
    names: list[str]
    category: str
    description: str = ""
    postCount: int = 0

    def to_resource(self) -> resources.InternalPool:
        kwargs = {}

        if self.id:
            kwargs["id"] = self.id
        if self.names:
            kwargs["names"] = self.names
        if self.category:
            kwargs["category"] = self.category

        return resources.InternalPool(**kwargs)

@dataclass(kw_only=True)
class Comment(SzurubooruResource):
    version: int
    id: int
    postId: int
    user: MicroUser
    text: str
    creationTime: str
    lastEditTime: str
    score: int
    ownScore: int

    @classmethod
    def from_dict(cls, data: dict):
        data = cls.filter_valid_keys(data=data)
        if 'user' in data and data['user']:
            data['user'] = MicroUser(**data['user'])
        return cls(**data)

@dataclass(kw_only=True)
class Note(SzurubooruResource):
    polygon: list[list[int]]
    text: str

@dataclass(kw_only=True)
class User(SzurubooruResource):
    version: int
    email: str
    rank: Literal["restricted", "regular", "power", "moderator", "administrator"]
    lastLoginTime: str
    creationTime: str
    avatarStyle: Literal["gravatar", "manual"]
    commentCount: int
    uploadedPostCount: int
    likedPostCount: int
    dislikedPostCount: int
    favoritePostCount: int

@dataclass(kw_only=True)
class Tag(MicroTag):
    version: int
    implications: list[MicroTag] = field(default_factory=list)
    suggestions: list[MicroTag] = field(default_factory=list)
    creationTime: str = ""
    lastEditTime: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict):
        data = cls.filter_valid_keys(data=data)
        if 'implications' in data and data['implications']:
            data['implications'] = [MicroTag(**tag) for tag in data['implications']]
        if 'suggestions' in data and data['suggestions']:
            data['suggestions'] = [MicroTag(**tag) for tag in data['suggestions']]
        return cls(**data)

    def to_resource(self) -> resources.InternalTag:
        kwargs = {
            "_extra": {
                "szurubooru": {}
            }
        }

        if self.names:
            kwargs["names"] = self.names
        if self.category:
            kwargs["category"] = self.category
        if self.implications:
            kwargs["implications"] = [implication.to_resource() for implication in self.implications]

        if self.version:
            kwargs["_extra"]["szurubooru"]["version"] = self.version

        return resources.InternalTag(**kwargs)

@dataclass(kw_only=True)
class Post(MicroPost):
    version: int
    creationTime: str
    lastEditTime: str
    safety: Literal["safe", "sketchy", "unsafe"]
    source: str = ""
    type: Literal["image", "animation", "video", "flash", "youtube"]
    checksum: str
    checksumMD5: str
    canvasWidth: str
    canvasHeight: str
    contentUrl: str
    thumbnailUrl: str
    flags: list[str]
    tags: list[MicroTag]
    relations: list[MicroPost]
    notes: Note
    user: MicroUser
    score: int
    ownScore: int
    ownFavorite: bool
    tagCount: int
    favoriteCount: int
    commentCount: int
    noteCount: int
    featureCount: int
    relationCount: int
    lastFeatureTime: str
    favoritedBy: list[MicroUser]
    hasCustomThumbnail: bool
    mimeType: str
    comments: list[Comment]
    pools: list[MicroPool]

    @property
    def sources(self) -> list[str]:
        if not self.source:
            return []
        split_sources:list[str] = self.source.split("\n")
        sources = [source.strip() for source in split_sources]
        return sources

    @classmethod
    def from_dict(cls, data: dict):
        data = cls.filter_valid_keys(data=data)
        if 'tags' in data and data['tags']:
            data['tags'] = [MicroTag(**tag) for tag in data['tags']]
        if 'relations' in data and data['relations']:
            data['relations'] = [MicroPost(**post) for post in data['relations']]
        if 'favoritedBy' in data and data['favoritedBy']:
            data['favoritedBy'] = [MicroUser(**user) for user in data['favoritedBy']]
        if 'comment' in data and data['comment']:
            data['comment'] = [Comment(**comment) for comment in data['comment']]
        if 'pools' in data and data['pools']:
            data['pools'] = [MicroPool(**pool) for pool in data['pools']]
        return cls(**data)

    def to_resource(self) -> resources.InternalPost:
        kwargs = {
            "_extra": {
                "szurubooru": {}
            }
        }

        if self.id:
            kwargs["id"] = self.id
        if self.tags:
            kwargs["tags"] = [tag.to_resource() for tag in self.tags]
        kwargs["sources"] = self.sources
        if self.creationTime:
            kwargs["created_at"] = datetime.fromisoformat(self.creationTime)
        if self.lastEditTime:
            kwargs["updated_at"] = datetime.fromisoformat(self.lastEditTime)
        # if self.relations:
        #     kwargs["relations"] = self.relations
        if self.safety:
            kwargs["safety"] = self.safety
        if self.checksum:
            kwargs["sha1"] = self.checksum
        if self.checksumMD5:
            kwargs["md5"] = self.checksumMD5
        if self.pools:
            kwargs["pools"] = [pool.to_resource() for pool in self.pools]

        kwargs["category"] = "szurubooru"

        if self.version:
            kwargs["_extra"]["szurubooru"]["version"] = self.version

        return resources.InternalPost(**kwargs)

@dataclass(kw_only=True)
class Pool(MicroPool):
    version: int
    posts: list[MicroPost]
    creationTime: str
    lastEditTime: str

    def to_resource(self) -> resources.InternalPool:
        kwargs = {
            "_extra": {
                "szurubooru": {}
            }
        }

        if self.id:
            kwargs["id"] = self.id
        if self.names:
            kwargs["names"] = self.names
        if self.category:
            kwargs["category"] = self.category
        if self.description:
            kwargs["description"] = self.description
        if self.posts:
            kwargs["posts"] = [posts.to_resource() for posts in self.posts]
        if self.creationTime:
            kwargs["created_at"] = datetime.fromisoformat(self.creationTime)
        if self.lastEditTime:
            kwargs["updated_at"] = datetime.fromisoformat(self.lastEditTime)
        
        if self.version:
            kwargs["_extra"]["szurubooru"]["version"] = self.version

        return resources.InternalPool(**kwargs)

T = TypeVar("T")

@dataclass(kw_only=True)
class PagedSearch(Generic[T], SzurubooruResource):
    offset: int
    limit: int
    total: int
    query: str = ""
    results: list[SzurubooruResource] = field(default_factory=list)

    def __str__(self) -> str:
        resource_string = f"query={self.query}, offset={self.offset}, limit={self.limit}, total={self.total}, results_count={len(self.results)}"
        return resource_string

    @classmethod
    def from_dict(cls, data: dict, resource_type:SzurubooruResource) -> "PagedSearch":
        data = cls.filter_valid_keys(data=data)
        if 'results' in data and data['results']:
            data['results'] = [resource_type.from_dict(item) for item in data['results']]
        return cls(**data)

@dataclass(kw_only=True)
class ImageSearch(Generic[T], SzurubooruResource):
    exact_post: Optional[Post] = None
    similar_posts: Optional[list[dict[str, Type]]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ImageSearch":
        data = cls.filter_valid_keys(data=data)
        if 'exact_post' in data and data['exact_post']:
            data['exact_post'] = Post.from_dict(data['exact_post'])
        if 'similar_posts' in data and data['similar_posts']:
            similar_posts = []
            for raw_post in data['similar_posts']:
                post = Post.from_dict(raw_post["post"])
                distance = raw_post["distance"]
                similar_posts.append(
                    {
                        "post": post,
                        "distance": distance
                    }
                )
            data['similar_posts'] = similar_posts

        return cls(**data)


class SharedAttributes:
    _DOMAINS = []
    _CATEGORY = [
        "szurubooru"
    ]
    _NAME = "szurubooru"

    URL_BASE = ""
    
    @property
    def DEFAULT_POST_SEARCH_URL(self):
        return f"{self.URL_BASE}/posts"

class SzurubooruMeta(SharedAttributes, _plugin_template.MetadataPlugin):
    def get_post_url(self, metadata:dict) -> str:
        post_id = metadata["id"]
        url = f"{self.URL_BASE}/post/{post_id}"
        logger.debug(f"Generated the post URL '{url}'")
        return url
    
    def get_safety(self, metadata: dict) -> str:
        safety = metadata.get("rating", "safe")
        return safety

class SzurubooruClient(SharedAttributes, _plugin_template.ApiPlugin):
    def __init__(self) -> None:
        self.image_distance_threshold = 0.15
        logger.debug(f'url_base = {self.URL_BASE}')
    
    @property
    def token(self):
        token = self.encode_auth_headers(self.username, self.password)
        return token
    
    @property
    def headers(self):
        headers = {"Accept": "application/json", "Authorization": f"Token {self.token}"}
        return headers

    def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        if post.md5:
            search_query = f"md5:{post.md5}"
            post_search = self._post_search(
                search_query=search_query,
                search_size=1
            )
            try:
                post:Post = post_search.results[0]
                return post.to_resource()
            except IndexError:
                logger.debug("Post not found with md5")

        for source in post.sources_of_type(desired_source_type=constants.SourceTypes.POST):
            search_query = f"source:{source}"
            post_search = self._post_search(
                search_query=search_query,
                search_size=1
            )
            try:
                post:Post = post_search.results[0]
                return post.to_resource()
            except IndexError:
                logger.debug("Post not found with source link")
        
        return None
    
    def find_similar_posts(self, post:resources.InternalPost) -> list[resources.InternalPost]:
        content_token = self._upload_temporary_file(file=post.local_file)
        post._extra[self._NAME]["content_token"] = content_token
        image_search = self._reverse_image_search(content_token=content_token)

        if image_search.exact_post:
            return [image_search.exact_post.to_resource()]

        if image_search.similar_posts:
            closest_posts:list[dict] = [post for post in image_search.similar_posts if post["distance"] < self.image_distance_threshold]
            sorted_posts:list[dict] = sorted(closest_posts, key=lambda x: x["distance"])

            posts:list[Post] = []
            for post in sorted_posts:
                post_resource:resources.InternalPost = post["post"].to_resource()
                post_resource._extra[self._NAME]["distance"] = post["distance"]
                posts.append(post_resource)
            return posts
        
        return []
    
    def find_posts_from_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalPost]:
        tag_str_list:list[str] = [urllib.parse.quote(str(tag)) for tag in tags]
        search_query = " ".join(tag_str_list)

        post_search = self._post_search(
            search_query=search_query
        )

        posts = [post.to_resource() for post in post_search.results]

        return posts
    
    def find_exact_tag(self, tag:resources.InternalTag) -> resources.InternalTag|None:
        tag_str_list:list[str] = [urllib.parse.quote(str(tag)) for tag in tag.names]

        for tag_str in tag_str_list:
            found_tag = self._get_tag(tag=tag_str)
            if found_tag:
                return found_tag
        return None
    
    def get_all_tags(self) -> list[resources.InternalTag]:
        raise NotImplementedError
    
    def get_all_pools(self) -> list[resources.InternalPool]:
        raise NotImplementedError

    def push_tag(self, tag:resources.InternalTag, force_update:bool=False) -> resources.InternalTag:
        tag_name = tag.names[0]
        destination_tag = self._get_tag(tag=tag_name)

        if not destination_tag:
            logger.info(f"Tag {tag_name} doesn't exist, creating")
            new_tag = self._create_tag(
                names=tag.names,
                tag_category=tag.category
            )
            return new_tag.to_resource()

        tag_category_match = destination_tag.category == tag.category
        tag_names_match = destination_tag.names == tag.names
        if tag_category_match and tag_names_match:
            logger.debug(f"Skipping update on tag '{tag_name}' as it already matches")
            return destination_tag.to_resource()

        merged_names = list(set(tag.names + destination_tag.names))
        new_tag = self._update_tag(
            version_id=destination_tag.version,
            names=merged_names,
            tag_category=tag.category
        )

        return new_tag.to_resource()

    def push_post(self, post:resources.InternalPost, force_update:bool=False) -> resources.InternalPost:
        if post.local_file:
            if not post._extra.get(self._NAME, {}).get("content_token"):
                similar_posts = self.find_similar_posts(post=post)
            else:
                similar_posts = []

            if not similar_posts:
                new_post = self._create_post(post=post)
                return new_post.to_resource()

            min_distance = similar_posts[0]._extra[self._NAME].get("distance", "??")
            max_distance = similar_posts[-1]._extra[self._NAME].get("distance", "??")

            if not force_update:
                logger.info(f"{len(similar_posts)} similar posts already exist in range {min_distance}-{max_distance}, update disabled, skipping")
                return None

            logger.info(f"{len(similar_posts)} similar posts already exist in range {min_distance}-{max_distance}, updating")
            new_post = self._update_post(
                original_post=similar_posts[0],
                new_post=post
            )
            return new_post.to_resource()
        
        exact_post = self.find_exact_post(post=post)
        new_post = self._update_post(
            original_post=exact_post,
            new_post=post
        )
        return new_post.to_resource()

    def push_pool(self, pool:resources.InternalPool, force_update:bool=False) -> resources.InternalPool:
        raise NotImplementedError

    def _escape_string(self, string:str) -> str:
        characters_to_escape = ["\\", "*", ":", "-", "."]
            
        escaped_string = ""
        for char in string:
            if char in characters_to_escape:
                escaped_string += "\\" + char  # Prepend backslash
            else:
                escaped_string += char  # Leave unchanged
        
        return escaped_string

    def _post_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Post]:
        url = f"{self.URL_BASE}/api/posts/"

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

        post_search:PagedSearch[Post] = PagedSearch.from_dict(data=response.json(), resource_type=Post)

        return post_search

    def _tag_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Tag]:
        url = f"{self.URL_BASE}/api/tags/"
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

        tag_search:PagedSearch[Tag] = PagedSearch.from_dict(data=response.json(), resource_type=Tag)

        return tag_search

    def _pool_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Pool]:
        url = f"{self.URL_BASE}/api/pools/"
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

        pool_search:PagedSearch[Pool] = PagedSearch.from_dict(data=response.json(), resource_type=Pool)
        
        return pool_search

    def _get_tag(self, tag:str) -> Tag|None:
        safe_tag = urllib.parse.quote(tag)
        url = f"{self.URL_BASE}/api/tag/{safe_tag}"

        response = requests.get(
            url=url,
            headers=self.headers
        )

        response_json = response.json()

        if response_json:
            tag = Tag.from_dict(response_json)
            return tag
        
        return None

    def _create_tag(self, names:list[str], tag_category:str="") -> Tag:
        url = f"{self.URL_BASE}/api/tags"

        data = {
            "names": names,
            "category": tag_category
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        tag = Tag.from_dict(response.json())

        return tag

    def _update_tag(self, version_id:int, names:list[str], tag_category:str="") -> Tag:
        url = f"{self.URL_BASE}/api/tag/{names[0]}"

        data = {
            "version": version_id,
            "category": tag_category,
            "names": names
        }

        response = requests.put(
            url=url,
            json=data,
            headers=self.headers
        )

        tag = Tag.from_dict(response.json())

        return tag

    def _create_post(self, post:resources.InternalPost) -> Post:
        url = f"{self.URL_BASE}/api/posts/"

        data = {
            "tags": post.str_tags,
            "safety": post.safety,
            "source": "\n".join(post.sources),
            "contentToken": post._extra[self._NAME]["content_token"]
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        post = Post.from_dict(response.json())

        return post

    def _update_post(self, original_post:resources.InternalPost, new_post:resources.InternalPost) -> Post:
        url = f"{self.URL_BASE}/api/post/{original_post.id}"

        data = {
            "version": original_post._extra[self._NAME]["version"],
            "tags": new_post.str_tags,
            "safety": new_post.safety,
            "source": "\n".join(new_post.sources)
        }

        content_token = new_post._extra[self._NAME].get("content_token")
        if content_token:
            data["contentToken"] = content_token

        response = requests.put(
            url=url,
            json=data,
            headers=self.headers
        )

        post = Post.from_dict(response.json())

        return post

    def _upload_temporary_file(self, file:Path) -> str:
        """Upload the provided file to the Szurubooru temporary upload endpoint

        Args:
            file (Path): The file to be uploaded

        Returns:
            token (str): The content token to be used for referencing the temporary file
        """
        url = f"{self.URL_BASE}/api/uploads"

        with open(file, "rb") as file_content:
            files = {"content": (file.name, file_content)}
            response = requests.post(
                url=url, 
                files=files,
                headers=self.headers
            )

        token:str = response.json()["token"]
        
        logger.debug(f"Uploaded file to temporary endpoint with token={token}")
        return token

    def _reverse_image_search(self, content_token:str) -> ImageSearch[Post]:
        logger.debug("Doing reverse image search")
        url = f"{self.URL_BASE}/api/posts/reverse-search"

        data = {
            "contentToken": content_token
        }

        response = requests.post(
            url=url,
            json=data,
            headers=self.headers
        )

        image_search:ImageSearch[Post] = ImageSearch.from_dict(data=response.json())

        return image_search
