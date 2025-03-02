from pathlib import Path
from fractions import Fraction

ROOT_FOLDER = Path(__file__).parent.parent
TEMP_FOLDER = Path("tmp")

class TagCategory:
    GENERAL = "general"
    ARTIST = "artist"
    CONTRIBUTOR = "contributor"
    COPYRIGHT = "copyright"
    CHARACTER = "character"
    SPECIES = "species"
    INVALID = "invalid"
    META = "meta"
    LORE = "lore"
    _DEFAULT = GENERAL

    HEX_COLOURS = {
        GENERAL: "#24aadd",
        ARTIST: "#ffbc05",
        CONTRIBUTOR: "#ff8604",
        COPYRIGHT: "#820d8f",
        CHARACTER: "#0e8f17",
        SPECIES: "#8c1b1b",
        INVALID: "#24aadd",
        META: "#8f8f8f",
        LORE: "#77c9bd",
    }

    ORDER = [
        GENERAL,
        ARTIST,
        CONTRIBUTOR,
        COPYRIGHT,
        CHARACTER,
        SPECIES,
        INVALID,
        META,
        LORE
    ]

    @classmethod
    def get_category_colour(cls, category:str) -> str:
        try:
            colour = cls.HEX_COLOURS[category]
        except KeyError:
            colour = cls.HEX_COLOURS[cls._DEFAULT]
        return colour

    @classmethod
    def get_category_order_position(cls, category:str) -> int:
        return cls.ORDER.index(category)

class Safety:
    SAFE = "safe"
    SKETCHY = "sketchy"
    UNSAFE = "unsafe"
    _DEFAULT = SAFE

    @classmethod
    def get_matching_safety(cls, safety:str, return_default=True):
        for name, value in vars(cls).items():
            if not isinstance(value, str):
                continue
            if safety.lower() == value.lower():
                return value
        if return_default:
            return cls._DEFAULT
        return None

class SourceTypes:
    GLOBAL = "Global"
    AUTHOR = "Author"
    POST = "Post"
    POOL = "Pool"
    UNKNOWN = "Unknown"
    _DEFAULT = UNKNOWN

class Thumbnails:
    SWF = ROOT_FOLDER / Path("images/thumbnails/swf.png")

    @classmethod
    def get_default_thumbnail(cls, file_extension:str) -> Path|None:
        for name, value in vars(cls).items():
            file_extension = file_extension.replace(".", "")
            if file_extension.lower() in name.lower():
                return value
        return None

class ImageResolutionTags:
    class ResolutionGroup:
        def __init__(self, name:str, width:int, height:int, comparison:str):
            self.name = name
            self.width = width
            self.height = height
            self.comparison = comparison

    THUMBNAIL = ResolutionGroup(name="thumbnail", width=250, height=250, comparison="lower")
    LOW_RES = ResolutionGroup(name="low_res", width=500, height=500, comparison="lower")
    HI_RES = ResolutionGroup(name="hi_res", width=1600, height=1200, comparison="higher")
    ABSURD_RES = ResolutionGroup(name="absurd_res", width=3200, height=2400, comparison="higher")
    SUPERABSURD_RES = ResolutionGroup(name="superabsurd_res", width=10000, height=10000, comparison="higher")

    @classmethod
    def get_tag_strings(cls, height:int, width:int) -> list[str]:
        tags = []
        for name, resolution_group in vars(cls).items():
            if not isinstance(resolution_group, cls.ResolutionGroup):
                continue
            if resolution_group.comparison == "lower":
                under_max_height = height <= resolution_group.height
                under_max_width = width <= resolution_group.width
                if under_max_height or under_max_width:
                    tags.append(resolution_group.name)
            elif resolution_group.comparison == "higher":
                over_min_height = height >= resolution_group.height
                over_min_width = width >= resolution_group.width
                if over_min_height or over_min_width:
                    tags.append(resolution_group.name)
        
        aspect_ratio = cls.get_aspect_ratio(height, width)
        tags.append(f"{aspect_ratio[0]}:{aspect_ratio[1]}")
        return tags

    @staticmethod
    def get_aspect_ratio(height:int, width:int) -> tuple[int, int]:
        ratio = Fraction(width, height).limit_denominator()
        width_ratio = ratio.numerator
        height_ratio = ratio.denominator
        return [width_ratio, height_ratio]

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]