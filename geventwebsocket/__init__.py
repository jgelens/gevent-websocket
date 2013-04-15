VERSION = (0, 4, 0, 'alpha', 0)


def get_version(*args, **kwargs):
    from .utils import get_version
    return get_version(*args, **kwargs)


from .resource import WebSocketApplication, Resource
from .server import WebSocketServer
from .exceptions import WebSocketError

__all__ = [WebSocketApplication, Resource, WebSocketServer, WebSocketError,
           get_version]
