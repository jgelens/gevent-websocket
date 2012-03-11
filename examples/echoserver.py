import os
from gevent.pywsgi import WSGIServer
import geventwebsocket


def echo(environ, start_response):
    websocket = environ.get("wsgi.websocket")
    if websocket is None:
        return http_handler(environ, start_response)
    try:
        while True:
            message = websocket.receive()
            if message is None:
                break
            websocket.send(message)
        websocket.close()
    except geventwebsocket.WebSocketError, ex:
        print "%s: %s" % (ex.__class__.__name__, ex)


def http_handler(environ, start_response):
    if environ["PATH_INFO"].strip("/") == "version":
        start_response("200 OK", [])
        return [agent]
    else:
        start_response("400 Bad Request", [])
        return ["WebSocket connection is expected here."]


path = os.path.dirname(geventwebsocket.__file__)
agent = "gevent-websocket/%s" % (geventwebsocket.__version__)
print "Running %s from %s" % (agent, path)
WSGIServer(("", 8000), echo, handler_class=geventwebsocket.WebSocketHandler).serve_forever()
