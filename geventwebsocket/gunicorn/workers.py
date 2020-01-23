from geventwebsocket.handler import WebSocketHandler
from gunicorn.workers.ggevent import GeventPyWSGIWorker, PyWSGIHandler


# Using gunicorn's PyWSGIHandler one can get working access logs, even when using gevent-websocket
class _Handler(PyWSGIHandler, WebSocketHandler):
    pass


class GeventWebSocketWorker(GeventPyWSGIWorker):
    wsgi_handler = _Handler
