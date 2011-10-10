
version_info = (0, 3, 0, 'dev')
__version__ =  ".".join(map(str, version_info))

try:
    from geventwebsocket.websocket import WebSocketVersion7, WebSocketLegacy
except ImportError:
    import traceback
    traceback.print_exc()
