
version_info = (0, 2, 3)
__version__ =  ".".join(map(str, version_info))

try:
    from geventwebsocket.websocket import WebSocket
    from geventwebsocket.websocket import WebSocketVersion7
except ImportError:
    import traceback
    traceback.print_exc()
