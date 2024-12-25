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
            return self._DEFAULT
        return None

class SourceTypes:
    GLOBAL = "Global"
    AUTHOR = "Author"
    POST = "Post"
    POOL = "Pool"
    UNKNOWN = "Unknown"
    _DEFAULT = UNKNOWN