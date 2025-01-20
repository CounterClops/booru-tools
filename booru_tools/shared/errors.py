from typing import TypeVar, ParamSpec, Callable, Awaitable, Any
from loguru import logger
import asyncio
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

class ContentTooLarge(Exception):
    pass

class TooManyRequestsError(Exception):
    pass

class InternalServerError(Exception):
    pass

class ServiceUnavailable(Exception):
    pass

class GatewayTimeout(Exception):
    pass

HTTP_CODE_MAP = {
    413: ContentTooLarge,
    429: TooManyRequestsError,
    500: InternalServerError,
    503: ServiceUnavailable,
    504: GatewayTimeout
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

class RetryOnExceptions:
    def __init__(self, exceptions:list[Exception]=[GatewayTimeout, ServiceUnavailable, TooManyRequestsError], wait_time:int=30, retry_limit:int=6):
        self.wait_time = wait_time
        self.retry_limit = retry_limit
        self.exceptions = tuple(exceptions)

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            try:
                return await func(*args, **kwargs)
            except self.exceptions as e:
                logger.debug(f"{e}")
                attempt_count = 1
                while attempt_count < self.retry_limit:
                    try:
                        logger.debug(f"Retrying in {self.wait_time}s")
                        await asyncio.sleep(self.wait_time)
                        return await func(*args, **kwargs)
                    except self.exceptions as e:
                        logger.debug(f"Encountered '{e}', on attempt {attempt_count}")
                        attempt_count += 1
        return wrapper