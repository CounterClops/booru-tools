class InvalidTagCategory(Exception):
    pass

class MissingMd5(Exception):
    pass

class NoPluginFound(Exception):
    pass

class PostExists(Exception):
    pass

class MissingFile(Exception):
    pass

### HTTP errors

class InternalServerError(Exception):
    pass

class TooManyRequestsError(Exception):
    pass

HTTP_CODE_MAP = {
    429: TooManyRequestsError,
    500: InternalServerError
}