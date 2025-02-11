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

class BadRequest(Exception):
    pass

class Conflict(Exception):
    pass

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
    400: BadRequest,
    409: Conflict,
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

def suppress_errors(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> R:
        try:
            return await func(*args, **kwargs)
        except Exception as error:
            error_message = f"Supressing {error} when running {func.__name__}"
            logger.warning(error_message)
    return wrapper

class RetryOnExceptions:
    def __init__(self, exceptions:list[Exception]=[GatewayTimeout, ServiceUnavailable, TooManyRequestsError], wait_time:int=30, retry_limit:int=6):
        self.wait_time = wait_time
        self.retry_limit = retry_limit
        self.exceptions = tuple(exceptions)
        self.last_error_message = ""

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            try:
                return await func(*args, **kwargs)
            except self.exceptions as e:
                logger.debug(f"{e}")
                attempt_count = 1
                while attempt_count < self.retry_limit:
                    wait_time = self.wait_time*attempt_count
                    try:
                        logger.debug(f"Retrying in {wait_time}s")
                        await asyncio.sleep(wait_time)
                        return await func(*args, **kwargs)
                    except self.exceptions as e:
                        logger.debug(f"Encountered '{e}', on attempt {attempt_count}")
                        attempt_count += 1
                        self.last_error_message = e
                    except Conflict as e:
                        logger.warning(f"HTTP Conflict error when calling {func.__name__}, due to '{e}'")
                        logger.debug(f"Stopping retry attempts as this is a HTTP conflict error")
                logger.error(f"Retry limit reached when calling {func.__name__}, due to '{e}'")
                logger.debug(f"Failure limit was reached when calling {func.__name__}, with args={args}, kwargs={kwargs}")
                logger.debug(traceback.format_exc())
                raise e
        return wrapper