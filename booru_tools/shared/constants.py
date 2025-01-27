from pathlib import Path

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

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]