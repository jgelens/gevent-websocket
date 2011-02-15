
version_info = (0, 2, 2)
__version__ =  ".".join(map(str, version_info))

try:
    from geventwebsocket.websocket import WebSocket
except ImportError:
    import traceback
    traceback.print_exc()
