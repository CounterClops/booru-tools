from boorus.shared import errors, meta, api_client
from loguru import logger

class E621Meta(meta.CommonBooru):
    _DOMAINS = [
        "e621.net"
    ]
    _CATEGORY = [
        "e621"
    ]
    _NAME = "e621"

    def __init__(self, config:dict={}):
        logger.debug(f"Loaded {self.__class__.__name__}")
        self.url_base = "https://e621.net"
        self.safety_mapping = {
            "safe": "safe",
            "s": "safe",
            "questionable": "sketchy",
            "q": "sketchy",
            "explicit": "unsafe",
            "e": "unsafe"
        }
        self.import_config(config=config)

    def validate_tag_category(self, tag_category) -> str:
        """Validate that the tag category is allowed

        Args:
            tag_category (Any): The tag category you'd like to validate

        Raises:
            errors.InvalidTagCategory: The tag category is invalid

        Returns:
            str: The valid tag category
        """
        if isinstance(tag_category, str):
            return tag_category
        raise errors.InvalidTagCategory

    def get_tags(self, metadata: dict) -> list:
        all_tags = []

        for tags in metadata['tags'].values():
            all_tags.extend(tags)
        
        logger.debug(f"Found {len(all_tags)} tags")
        return all_tags
    
    def get_md5(self, metadata: dict) -> str:
        metadata_file = metadata.get("file", {})
        try:
            md5 = metadata_file["md5"]
        except KeyError:
            raise errors.MissingMd5
        
        logger.debug(f"Found '{md5}' md5")
        return md5

    def add_tag_category_map(self, metadata: dict) -> dict:
        tag_category_map = {}
        for category, tags in metadata["tags"].items():
            try:
                category = self.validate_tag_category(category)
            except errors.InvalidTagCategory:
                continue

            for tag in tags:
                tag_category_map[tag] = category
        
        logger.debug(f"Adding {len(tag_category_map.keys())} tag categories to metadata")
        metadata['tag_category_map'] = tag_category_map
        return metadata
    
    def add_post_url(self, metadata:dict) -> dict:
        post_url = self.generate_post_url(metadata=metadata)
        metadata["post_url"] = post_url
        return metadata

    def generate_post_url(self, metadata:dict) -> str:
        post_id = metadata['id']
        url = f"{self.url_base}/posts/{post_id}"
        logger.debug(f"Generated the post URL '{url}'")
        return url

class E621Client(api_client.ApiClient):
    _DOMAINS = [
        "e621.net"
    ]
    _CATEGORY = [
        "e621"
    ]
    _NAME = "e621"

    def __init__(self, config:dict={}) -> None:
        self.url_base = "https://e621.net"
        self.headers = {'Accept': 'application/json'}
        self.import_config(config=config)

    def get_pools(self, ):
        pass