from typing import TypeVar, ParamSpec, Callable, Awaitable, Any
from loguru import logger
import functools
import traceback

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

P = ParamSpec("P")
R = TypeVar('R')

def log_all_errors(func: Callable[P, Awaitable[R]], reraise_errors:bool=False) -> Callable[P, Awaitable[R]]:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> R:
        try:
            return await func(*args, **kwargs)
        except Exception as error:
            error_message = f"{error} when running {func.__name__}"
            logger.critical(error_message)
            logger.critical(traceback.format_exc())
            if reraise_errors:
                raise error
    return wrapper