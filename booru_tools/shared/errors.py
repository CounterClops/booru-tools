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

class InternalServerError(Exception):
    pass

# class HttpRetyLater(Exception):
#     def __init__(self, message:str="Retry later", delay_time:int=60, retry_limit:int=6):
#         self.message = message
#         self.delay_time = delay_time
#         self.retry_limit = retry_limit
#         super().__init__(self.message)