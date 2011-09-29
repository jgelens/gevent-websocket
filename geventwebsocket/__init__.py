
version_info = (0, 3, 0, 'dev')
__version__ =  ".".join(map(str, version_info))

try:
    from geventwebsocket.websocket import WebSocket, WebSocketLegacy
except ImportError:
    import traceback
    traceback.print_exc()
