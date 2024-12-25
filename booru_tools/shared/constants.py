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

class SourceTypes:
    GLOBAL = "Global"
    AUTHOR = "Author"
    POST = "Post"
    POOL = "Pool"
    UNKNOWN = "Unknown"
    _DEFAULT = UNKNOWN