version_info = (0, 3, 6)
__version__ = ".".join(map(str, version_info))

__all__ = ['WebSocketHandler', 'WebSocketError']

from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocketError
