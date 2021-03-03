VERSION = (0, 11, 0, 'final', 0)

__all__ = [
    'WebSocketApplication',
    'Resource',
    'WebSocketServer',
    'WebSocketError',
    'get_version',
    'VERSION',
]


def get_version(*args, **kwargs):
    from .utils import get_version
    return get_version(*args, **kwargs)


try:
    from .resource import WebSocketApplication, Resource
    from .server import WebSocketServer
    from .exceptions import WebSocketError
except ImportError:
    pass
