from dataclasses import dataclass, field, fields
from typing import Optional, Literal, Type, Generic, TypeVar, ParamSpec, Callable, Awaitable, Any
from pathlib import Path
from datetime import datetime
from loguru import logger
from async_lru import alru_cache
from aiolimiter import AsyncLimiter
from copy import deepcopy
import traceback

import urllib.parse
import asyncio
import aiohttp
import json
import functools

from booru_tools.plugins import _plugin_template
from booru_tools.shared import resources, errors, constants

class SzurubooruError(Exception):
    pass

class MissingRequiredFileError(SzurubooruError):
    pass

class MissingRequiredParameterError(SzurubooruError):
    pass

class InvalidParameterError(SzurubooruError):
    pass

class IntegrityError(SzurubooruError):
    pass

class SearchError(SzurubooruError):
    pass

class AuthError(SzurubooruError):
    pass

class PostNotFoundError(SzurubooruError):
    pass

class PostAlreadyFeaturedError(SzurubooruError):
    pass

class PostAlreadyUploadedError(SzurubooruError):
    pass

class InvalidPostIdError(SzurubooruError):
    pass

class InvalidPostSafetyError(SzurubooruError):
    pass

class InvalidPostSourceError(SzurubooruError):
    pass

class InvalidPostContentError(SzurubooruError):
    pass

class InvalidPostRelationError(SzurubooruError):
    pass

class InvalidPostNoteError(SzurubooruError):
    pass

class InvalidPostFlagError(SzurubooruError):
    pass

class InvalidFavoriteTargetError(SzurubooruError):
    pass

class InvalidCommentIdError(SzurubooruError):
    pass

class CommentNotFoundError(SzurubooruError):
    pass

class EmptyCommentTextError(SzurubooruError):
    pass

class InvalidScoreTargetError(SzurubooruError):
    pass

class InvalidScoreValueError(SzurubooruError):
    pass

class TagCategoryNotFoundError(SzurubooruError):
    pass

class TagCategoryAlreadyExistsError(SzurubooruError):
    pass

class TagCategoryIsInUseError(SzurubooruError):
    pass

class InvalidTagCategoryNameError(SzurubooruError):
    pass

class InvalidTagCategoryColorError(SzurubooruError):
    pass

class TagNotFoundError(SzurubooruError):
    pass

class TagAlreadyExistsError(SzurubooruError):
    pass

class TagIsInUseError(SzurubooruError):
    pass

class InvalidTagNameError(SzurubooruError):
    pass

class InvalidTagRelationError(SzurubooruError):
    pass

class InvalidTagCategoryError(SzurubooruError):
    pass

class InvalidTagDescriptionError(SzurubooruError):
    pass

class UserNotFoundError(SzurubooruError):
    pass

class UserAlreadyExistsError(SzurubooruError):
    pass

class InvalidUserNameError(SzurubooruError):
    pass

class InvalidEmailError(SzurubooruError):
    pass

class InvalidPasswordError(SzurubooruError):
    pass

class InvalidRankError(SzurubooruError):
    pass

class InvalidAvatarError(SzurubooruError):
    pass

class ProcessingError(SzurubooruError):
    pass

class ValidationError(SzurubooruError):
    pass

P = ParamSpec("P")
R = TypeVar('R')

class SzurubooruErrorHandler:
    def __init__(self) -> None:
        self.error_map = {
            "MissingRequiredFileError": MissingRequiredFileError,
            "MissingRequiredParameterError": MissingRequiredParameterError,
            "InvalidParameterError": InvalidParameterError,
            "IntegrityError": IntegrityError,
            "SearchError": SearchError,
            "AuthError": AuthError,
            "PostNotFoundError": PostNotFoundError,
            "PostAlreadyFeaturedError": PostAlreadyFeaturedError,
            "PostAlreadyUploadedError": PostAlreadyUploadedError,
            "InvalidPostIdError": InvalidPostIdError,
            "InvalidPostSafetyError": InvalidPostSafetyError,
            "InvalidPostSourceError": InvalidPostSourceError,
            "InvalidPostContentError": InvalidPostContentError,
            "InvalidPostRelationError": InvalidPostRelationError,
            "InvalidPostNoteError": InvalidPostNoteError,
            "InvalidPostFlagError": InvalidPostFlagError,
            "InvalidFavoriteTargetError": InvalidFavoriteTargetError,
            "InvalidCommentIdError": InvalidCommentIdError,
            "CommentNotFoundError": CommentNotFoundError,
            "EmptyCommentTextError": EmptyCommentTextError,
            "InvalidScoreTargetError": InvalidScoreTargetError,
            "InvalidScoreValueError": InvalidScoreValueError,
            "TagCategoryNotFoundError": TagCategoryNotFoundError,
            "TagCategoryAlreadyExistsError": TagCategoryAlreadyExistsError,
            "TagCategoryIsInUseError": TagCategoryIsInUseError,
            "InvalidTagCategoryNameError": InvalidTagCategoryNameError,
            "InvalidTagCategoryColorError": InvalidTagCategoryColorError,
            "TagNotFoundError": TagNotFoundError,
            "TagAlreadyExistsError": TagAlreadyExistsError,
            "TagIsInUseError": TagIsInUseError,
            "InvalidTagNameError": InvalidTagNameError,
            "InvalidTagRelationError": InvalidTagRelationError,
            "InvalidTagCategoryError": InvalidTagCategoryError,
            "InvalidTagDescriptionError": InvalidTagDescriptionError,
            "UserNotFoundError": UserNotFoundError,
            "UserAlreadyExistsError": UserAlreadyExistsError,
            "InvalidUserNameError": InvalidUserNameError,
            "InvalidEmailError": InvalidEmailError,
            "InvalidPasswordError": InvalidPasswordError,
            "InvalidRankError": InvalidRankError,
            "InvalidAvatarError": InvalidAvatarError,
            "ProcessingError": ProcessingError,
            "ValidationError": ValidationError
        }

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            try:
                return await func(*args, **kwargs)
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as error:
                logger.debug(f"HTTP Error {error.status}: '{error.message}'")
                try:
                    error_json:dict = json.loads(error.message)
                    szurubooru_error_name = error_json.get("name")
                    szurubooru_error_description = error_json.get("description")
                    szurubooru_error_class = self.error_map[szurubooru_error_name]
                    message = f"HTTP Error {error.status}: '{szurubooru_error_name}' {szurubooru_error_description}"
                    raise szurubooru_error_class(message)
                except json.decoder.JSONDecodeError as e:
                    szurubooru_error_class = errors.HTTP_CODE_MAP.get(error.status, None)
                    if szurubooru_error_class:
                        raise szurubooru_error_class(f"Failed to decode error message. Full response text is '{error.message}'")
                    logger.critical(f"Failed to decode error message. Full response text is '{error.message}'")
                    logger.critical(traceback.format_exc())
                    raise error
                except KeyError as e:
                    logger.critical(f"Encountered unknown aiohttp error '{e}'")
                    raise error
            except Exception as error:
                logger.error(f"Encountered unexpected error '{error}' in {func.__name__}")
                logger.error(traceback.format_exc())
                raise error
        return wrapper

class ValidateUniquePostTags:
    def __init__(self, post_param:str="post"):
        self.post_param = post_param

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            try:
                return await func(*args, **kwargs)
            except TagAlreadyExistsError as e:
                logger.error(f"{e}: Going to check for tag conflicts and attempt a re-run")
                func_self = args[0]
                post:resources.InternalPost = kwargs.pop(self.post_param)

                tag_names = []
                for tag in post.tags:
                    for name in tag.names:
                        if name in tag_names:
                            continue
                        tag_names.append(name)

                conflicting_tags:list[Tag] = await func_self._get_conflicting_tags(
                    names=post.tags
                )

                logger.debug(f"Found {len(conflicting_tags)} conflicting tags")
                for tag in conflicting_tags:
                    for name in tag.names:
                        if name in tag_names:
                            continue
                        tag_names.append(name)
                
                kwargs[self.post_param] = post
                return await func(*args, **kwargs)

        return wrapper

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
    def __init__(self, session: aiohttp.ClientSession = None) -> None:
        self.session = session
        self.image_distance_threshold = 0.10
        logger.debug(f'url_base = {self.URL_BASE}')
        self.rate_limiter = AsyncLimiter(
            max_rate=200,
            time_period=60
        )
    
    @property
    def token(self):
        token = self.encode_auth_headers(self.username, self.password)
        return token
    
    @property
    def headers(self):
        headers = {"Accept": "application/json", "Authorization": f"Token {self.token}"}
        return headers

    async def find_exact_post(self, post:resources.InternalPost) -> resources.InternalPost | None:
        if post.md5:
            search_query = f"md5:{post.md5}"
            post_search = await self._post_search(
                search_query=search_query,
                search_size=1
            )
            try:
                found_post:Post = post_search.results[0]
                logger.debug(f"Post found with md5: {found_post.checksumMD5}")
                return found_post.to_resource()
            except IndexError:
                logger.debug("Post not found with md5")

        # for source in post.sources_of_type(desired_source_type=constants.SourceTypes.POST):
        #     search_query = f"source:{source}"
        #     post_search = await self._post_search(
        #         search_query=search_query,
        #         search_size=1
        #     )
        #     try:
        #         found_post:Post = post_search.results[0]
        #         logger.debug(f"Post found with source: {source}")
        #         return found_post.to_resource()
        #     except IndexError:
        #         logger.debug("Post not found with source link")
        
        return None
    
    async def find_similar_posts(self, post:resources.InternalPost) -> list[resources.InternalPost]:
        try:
            content_token = await self._retrieve_content_token(post=post)
        except errors.MissingFile:
            return []
        
        image_search = await self._reverse_image_search(content_token=content_token)

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
    
    async def find_posts_from_tags(self, tags:list[resources.InternalTag]) -> list[resources.InternalPost]:
        tag_str_list:list[str] = [urllib.parse.quote(str(tag)) for tag in tags]
        search_query = " ".join(tag_str_list)

        post_search = await self._post_search(
            search_query=search_query
        )

        posts = [post.to_resource() for post in post_search.results]

        return posts
    
    async def find_exact_tag(self, tag:resources.InternalTag) -> resources.InternalTag|None:
        tag_str_list:list[str] = [urllib.parse.quote(str(tag)) for tag in tag.names]

        for tag_str in tag_str_list:
            found_tag:Tag = await self._get_tag(tag=tag_str)
            if found_tag:
                return found_tag
        return None
    
    async def get_all_tags(self) -> list[resources.InternalTag]:
        raise NotImplementedError
    
    async def get_all_pools(self) -> list[resources.InternalPool]:
        raise NotImplementedError

    @errors.log_all_errors
    @errors.RetryOnExceptions(
        exceptions=[IntegrityError],
        wait_time=30,
        retry_limit=6
    )
    async def push_tag(self, tag:resources.InternalTag, replace_tags:bool=False, create_empty_tags:bool=True) -> resources.InternalTag:       
        # Work around as szurubooru returns a 500 error if tag names exceed 190 names
        tag.names = tag.names[:189]
        
        conflicting_tags = await self._get_conflicting_tags(
            names=tag.names,
        )

        if not conflicting_tags:
            try:
                new_tag = await self._create_tag(tag=tag)
                return new_tag.to_resource()
            except TagAlreadyExistsError as e:
                logger.error(f"Tried to create tag '{tag}' but encountered unexpected error '{e}'")
                return None

        primary_tag = conflicting_tags[0]
        primary_tag_name = primary_tag.names[0]
        primary_tag_resource = primary_tag.to_resource()
        tag_changes = tag.diff(resource=primary_tag_resource)

        if not primary_tag.usages and not create_empty_tags:
            return None

        if not tag_changes:
            logger.debug(f"Skipping update on tag '{primary_tag_name}' as it already matches (Pre-conflict scan)")
            return primary_tag_resource
    
        for conflicting_tag in conflicting_tags[1:]:
            conflicting_tag_name = conflicting_tag.names[0]
            if not conflicting_tag.usages:
                logger.info(f"Deleting tag '{conflicting_tag_name}' as it conflicts with '{primary_tag_name}' and is unused")
                await self._delete_tag(tag=conflicting_tag)
                continue

            try:
                logger.info(f"Merging tag '{conflicting_tag_name}' into '{primary_tag.names[0]}'")
                await self._merge_tag(
                    from_tag=conflicting_tag, 
                    to_tag=primary_tag
                )
            except TagNotFoundError as error:
                await asyncio.sleep(5)
                conflicting_tag = self._correct_first_tag(
                    primary_tag_name=primary_tag_name,
                    tag=conflicting_tag
                )
                await self._merge_tag(
                    from_tag=conflicting_tag, 
                    to_tag=primary_tag
                )

        if replace_tags:
            desired_tag = primary_tag_resource.merge_resource(
                update_object=tag,
                allow_blank_values=True,
                merge_where_possible=False
            )
        else:
            desired_tag:resources.InternalTag = primary_tag_resource.merge_resource(update_object=tag)

        # Work around as szurubooru returns a 500 error if tag names exceed 190 names
        desired_tag.names = desired_tag.names[:189]

        proposed_tag_changes = desired_tag.diff(resource=tag)
        if not proposed_tag_changes:
            logger.debug(f"Skipping update on tag '{primary_tag_name}' as it already matches (Post-conflict scan)")
            return desired_tag

        try:
            desired_tag_name = desired_tag.names[0]
            logger.info(f"Updating tag '{desired_tag_name}' with names=({desired_tag.names}), category=({desired_tag.category}), implications=({desired_tag.implications})")
            new_tag = await self._update_tag(tag=desired_tag)
        except TagNotFoundError as error:
            desired_tag = self._correct_first_tag(
                primary_tag_name=primary_tag_name,
                tag=desired_tag
            )
            await asyncio.sleep(5)
            new_tag = await self._update_tag(tag=desired_tag)
        except InvalidTagRelationError as error:
            logger.error(f"Tag '{desired_tag_name}' update failed with {error}")
            return None
        except TagAlreadyExistsError as error:
            logger.error(f"Tag '{desired_tag_name}' update failed with {error}. This is likely due to tag alias also being added as implications")
            desired_tag_trimmed = deepcopy(desired_tag)
            desired_tag_trimmed.names = [desired_tag_name]
            logger.info(f"Temporarily setting tag {desired_tag_name} to 1 alias, before updating to include {desired_tag.names}")
            await self._update_tag(tag=desired_tag_trimmed)
            await asyncio.sleep(2)
            new_tag = await self._update_tag(tag=desired_tag)


        return new_tag.to_resource()

    @errors.log_all_errors
    async def push_post(self, post:resources.InternalPost, force_update:bool=False) -> resources.InternalPost:
        if post.local_file:
            try:
                content_token = await self._retrieve_content_token(post=post)
            except errors.MissingFile as error:
                logger.error(f"{error}: Local file was was set on '{post.id}' failed to get content_token")
                return None

            logger.debug(f"Content token found '{content_token}', doing reverse image search")
            similar_posts = await self.find_similar_posts(post=post)

            if not similar_posts:
                logger.debug("No similar posts found, creating new post")
                new_post = await self._create_post(post=post)
                return new_post.to_resource()

            closest_post = self._check_similar_posts_for_exact(posts=similar_posts)
            new_post = await self._update_post(
                original_post=closest_post,
                new_post=post
            )
            return new_post.to_resource()
        
        logger.debug("No local file found, looking for existing post")
        try:
            exact_post = await self.find_exact_post(post=post)
        except PostNotFoundError as error:
            logger.error(f"Encountered '{error}'. This shouldn't happen. Was trying to get {exact_post}")
            return None
        
        logger.debug(f"Updating post with id={exact_post.id}")
        ignored_fields = [
            "id",
            "category",
            "created_at",
            "updated_at",
            "sha1",
            "md5",
            "post_url",
            "description",
            "pools"
        ]
        changes = post.diff(resource=exact_post, fields_to_ignore=ignored_fields)
        if not changes:
            logger.debug(f"No changes found in post ({exact_post.id})")
            return None
        
        logger.debug(f"Changes found in post ({post.id}): {changes}")
        updated_post = await self._update_post(
            original_post=exact_post,
            new_post=post
        )
        return updated_post.to_resource()

    async def push_pool(self, pool:resources.InternalPool, force_update:bool=False) -> resources.InternalPool:
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

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _post_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Post]:
        url = f"{self.URL_BASE}/api/posts/"

        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        logger.debug(f"Searching for posts with query '{search_query}'")

        async with self.session.get(
                url=url,
                headers=self.headers,
                params=params
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        post_search:PagedSearch[Post] = PagedSearch.from_dict(data=response_json, resource_type=Post)

        return post_search

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _tag_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Tag]:
        url = f"{self.URL_BASE}/api/tags/"
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        logger.debug(f"Searching for tags with query '{search_query}'")

        async with self.session.get(
                url=url,
                headers=self.headers,
                params=params
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        tag_search:PagedSearch[Tag] = PagedSearch.from_dict(data=response_json, resource_type=Tag)

        return tag_search

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _pool_search(self, search_query:str, search_size:int=100, offset:int=0) -> PagedSearch[Pool]:
        url = f"{self.URL_BASE}/api/pools/"
        params = {
            "offset": offset,
            "limit": search_size,
            "query": search_query
        }

        logger.debug(f"Searching for pools with query '{search_query}'")

        async with self.session.get(
                url=url,
                headers=self.headers,
                params=params
            ) as response, self.rate_limiter:
            response_json = await response.json()

        pool_search:PagedSearch[Pool] = PagedSearch.from_dict(data=response_json, resource_type=Pool)
        
        return pool_search

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @alru_cache(maxsize=1024, ttl=15)
    @SzurubooruErrorHandler()
    async def _get_tag(self, tag:str) -> Tag|None:
        safe_tag = urllib.parse.quote(tag)
        url = f"{self.URL_BASE}/api/tag/{safe_tag}"

        logger.debug(f"Getting tag '{tag}'")

        async with self.session.get(
                url=url,
                headers=self.headers,
            ) as response:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        if response_json:
            tag = Tag.from_dict(response_json)
            return tag
        
        return None

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _create_tag(self, tag:resources.InternalTag) -> Tag:
        url = f"{self.URL_BASE}/api/tags"

        data = {
            "names": tag.names
        }

        if tag.category != constants.Category._DEFAULT:
            data["category"] = tag.category

        if tag.implications:
            implication_names = []
            for implication in tag.implications:
                implication_names.extend(implication.names)
            data["implications"] = list(set(implication_names))

        logger.debug(f"Creating tag '{tag.names[0]}' with data={[tag]}")

        async with self.session.post(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()
        
        tag = Tag.from_dict(response_json)

        return tag

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _update_tag(self, tag:resources.InternalTag) -> Tag:
        safe_tag = urllib.parse.quote(tag.names[0])
        url = f"{self.URL_BASE}/api/tag/{safe_tag}"

        data = {
            "version": tag._extra[self._NAME]["version"],
            "category": tag.category
        }

        if tag.names:
            data["names"] = list(tag.names)

        if tag.implications:
            implication_names = []
            for implication in tag.implications:
                implication_names.extend(implication.names)
            data["implications"] = list(set(implication_names))

        logger.debug(f"Attempting to update tag '{tag.names[0]}' with data={[tag]}")

        async with self.session.put(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        tag = Tag.from_dict(response_json)

        return tag

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _delete_tag(self, tag:Tag) -> None:
        safe_tag = urllib.parse.quote(tag.names[0])
        url = f"{self.URL_BASE}/api/tag/{safe_tag}"

        data = {
            "version": tag.version,
        }

        logger.debug(f"Attempting to delete tag '{tag.names[0]}' with version {tag.version}")

        async with self.session.delete(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()
        
        return None

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _merge_tag(self, from_tag:Tag, to_tag:Tag) -> Tag:
        url = f"{self.URL_BASE}/api/tag-merge/"

        from_tag_name = from_tag.names[0]
        to_tag_name = to_tag.names[0]

        data = {
            "removeVersion": from_tag.version,
            "remove": from_tag_name,
            "mergeToVersion": to_tag.version,
            "mergeTo": to_tag_name,
        }

        logger.debug(f"Attempting to merge tag '{from_tag_name}' [v{from_tag.version}] into {to_tag_name} [v{to_tag.version}]")

        async with self.session.post(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response_json = await response.json()
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err

        tag = Tag.from_dict(response_json)

        return tag
    
    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _get_conflicting_tags(self, names:list[str]) -> list[Tag]:
        conflicting_tags:list[Tag] = []
        all_found_names:set[str] = set()

        for name in names:
            if name in all_found_names:
                continue

            try:
                found_tag:Tag = await self._get_tag(tag=name)
            except TagNotFoundError:
                continue

            found_tag_names = set(found_tag.names)
            names_already_found = found_tag_names.issubset(all_found_names)

            logger.debug(f"Found a tag with the names {found_tag.names}")
            if names_already_found:
                continue

            logger.debug(f"Found conflicting tag with {found_tag.names}")
            conflicting_tags.append(found_tag)
            all_found_names.update(found_tag_names)

        return conflicting_tags
    
    def _correct_first_tag(self, primary_tag_name:str, tag:Tag|resources.InternalTag) -> Tag|resources.InternalTag:
        logger.error(f"First tag does not exist, moving primary tag '{primary_tag_name}' to first tag of {tag.names}")
        index_of_primary_tag = tag.names.index(primary_tag_name)
        primary_name_value = tag.names.pop(index_of_primary_tag)
        tag.names.insert(0, primary_name_value)

        return tag

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @ValidateUniquePostTags(post_param="post")
    @SzurubooruErrorHandler()
    async def _create_post(self, post:resources.InternalPost) -> Post:
        url = f"{self.URL_BASE}/api/posts/"

        try:
            content_token = await self._retrieve_content_token(post=post)
        except errors.MissingFile as error:
            logger.error(f"{error}: Local file was set on '{post.id}' failed to get content_token")
            return None

        data = {
            "tags": post.str_tags,
            "safety": post.safety,
            "source": "\n".join(post.sources),
            "contentToken": content_token
        }

        thumbnail_content_token = await self._upload_thumbnail(file=post.local_file)

        if thumbnail_content_token:
            data["thumbnailToken"]  = thumbnail_content_token

        logger.debug(f"Creating post with data={data}")

        async with self.session.post(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        post = Post.from_dict(response_json)

        return post

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @ValidateUniquePostTags(post_param="new_post")
    @SzurubooruErrorHandler()
    async def _update_post(self, original_post:resources.InternalPost, new_post:resources.InternalPost) -> Post:
        url = f"{self.URL_BASE}/api/post/{original_post.id}"

        post_version = original_post._extra[self._NAME]["version"]

        data = {
            "version": post_version,
            "tags": new_post.str_tags,
            "safety": new_post.safety,
            "source": "\n".join(new_post.sources)
        }

        # try:
        #     logger.debug(f"Checking for content_token in new post '{new_post.id}' for existing post '{original_post.id}' v{post_version}")
        #     content_token = await self._retrieve_content_token(post=new_post)
        #     data["contentToken"] = content_token
        # except errors.MissingFile as e:
        #     logger.debug(f"No new file to update existing post with")
        #     pass

        logger.debug(f"Updating post '{original_post.id}' with data={data}")

        async with self.session.put(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        post = Post.from_dict(response_json)

        return post
    
    def _check_similar_posts_for_exact(self, posts:list[resources.InternalPost]) -> Post|None:
        if not posts:
            return None
        
        min_distance = posts[0]._extra[self._NAME].get("distance", "??")
        max_distance = posts[-1]._extra[self._NAME].get("distance", "??")
        logger.debug(f"Checking similar posts ({len(posts)}) for exact match, distance range {min_distance}-{max_distance}")

        post = posts[0]
        post_distance:int = post._extra[self._NAME].get("distance", 1)

        if post_distance < self.image_distance_threshold:
            logger.info(f"Found similar post ({post.id}) with distance {post_distance} which is close enough to be exact")
            return post
        return None
    
    @SzurubooruErrorHandler()
    async def _retrieve_content_token(self, post:resources.InternalPost) -> str:
        content_token = post._extra[self._NAME].get("content_token")
        if content_token:
            logger.debug(f"Content token '{content_token}' found in post '{post.id}'")
            return content_token
        
        if post.local_file:
            logger.debug(f"Local file '{post.local_file}' found in post '{post.id}'")
            if not post.local_file.exists():
                logger.error(f"Local file '{post.local_file}' was found in post {post.id}, but the file doesn't exist in the filesystem")
                raise errors.MissingFile
            content_token = await self._upload_temporary_file(file=post.local_file)
            post._extra[self._NAME]["content_token"] = content_token
            return content_token
        
        logger.error(f"No local file or content token found in post '{post.id}'")
        raise errors.MissingFile
    
    async def _upload_thumbnail(self, file:Path) -> str:
        if not file:
            return None
        
        file_extension = file.suffix
        logger.debug(f"Getting thumbnail for file extension '{file_extension}'")

        thumbnail_file = constants.Thumbnails.get_default_thumbnail(
            file_extension=file_extension
        )

        if not thumbnail_file:
            logger.debug(f"No default thumbnail found for file extension '{file_extension}'")
            return None
        
        logger.info(f"Found default thumbnail for file extension '{file_extension}'")        
        thumbnail_content_token = await self._upload_temporary_file(file=thumbnail_file)
        return thumbnail_content_token

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _upload_temporary_file(self, file:Path) -> str:
        """Upload the provided file to the Szurubooru temporary upload endpoint

        Args:
            file (Path): The file to be uploaded

        Returns:
            token (str): The content token to be used for referencing the temporary file
        """
        url = f"{self.URL_BASE}/api/uploads"

        logger.debug(f"Uploading file '{file}' to temporary endpoint")

        with open(file, "rb") as file_content:
            form = aiohttp.FormData()
            form.add_field("content", file_content, filename=file.name)

            async with self.session.post(
                    url=url,
                    headers=self.headers,
                    data=form
                ) as response, self.rate_limiter:
                response_json = await response.json()
                try:
                    response.raise_for_status()
                except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                    err.message = await response.text()
                    raise err

        token:str = response_json["token"]
        
        logger.debug(f"Uploaded '{file}' to temporary endpoint with token={token}")
        return token

    @errors.RetryOnExceptions(
        exceptions=[errors.GatewayTimeout],
        wait_time=30,
        retry_limit=6
    )
    @SzurubooruErrorHandler()
    async def _reverse_image_search(self, content_token:str) -> ImageSearch[Post]:
        url = f"{self.URL_BASE}/api/posts/reverse-search"

        data = {
            "contentToken": content_token
        }

        logger.debug(f"Reverse image search with data={data}")

        async with self.session.post(
                url=url,
                headers=self.headers,
                json=data
            ) as response, self.rate_limiter:
            try:
                response.raise_for_status()
            except (aiohttp.ClientResponseError, aiohttp.ContentTypeError) as err:
                err.message = await response.text()
                raise err
            response_json = await response.json()

        image_search:ImageSearch[Post] = ImageSearch.from_dict(data=response_json)

        return image_search