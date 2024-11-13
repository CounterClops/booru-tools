from base64 import b64encode
from .base_classes import Base

class ApiClient(Base):
    @staticmethod
    def encode_auth_headers(user: str, token: str) -> str:
        """
        Encodes the authentication headers into base64

        This method encodes the authentication headers. It takes a user and a token, concatenates them with
        a colon in between, encodes the result in UTF-8, base64 encodes the result, and then decodes the result in ASCII.
        It returns the final result as a string.

        Args:
            user (str): The username.
            token (str): The token/password.

        Returns:
            str: The encoded authentication headers.
        """
        return b64encode(f'{user}:{token}'.encode()).decode('ascii')