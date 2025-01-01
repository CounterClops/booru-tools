class Category:
    GENERAL = "General"
    ARTIST = "Artist"
    CONTRIBUTOR = "Contributor"
    COPYRIGHT = "Copyright"
    CHARACTER = "Character"
    SPECIES = "Species"
    INVALID = "Invalid"
    META = "Meta"
    LORE = "Lore"
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