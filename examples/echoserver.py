import os

import geventwebsocket

from geventwebsocket.server import WebSocketServer



def echo_app(environ, start_response):
    websocket = environ.get("wsgi.websocket")

    if websocket is None:
        return http_handler(environ, start_response)
    try:
        while True:
            message = websocket.receive()
            websocket.send(message)
        websocket.close()
    except geventwebsocket.WebSocketError, ex:
        print "{0}: {1}".format(ex.__class__.__name__, ex)


def http_handler(environ, start_response):
    if environ["PATH_INFO"].strip("/") == "version":
        start_response("200 OK", [])
        return [agent]

    else:
        start_response("400 Bad Request", [])

        return ["WebSocket connection is expected here."]


path = os.path.dirname(geventwebsocket.__file__)
agent = "gevent-websocket/%s" % (geventwebsocket.get_version())

print "Running %s from %s" % (agent, path)
WebSocketServer(("", 8000), echo_app, debug=False).serve_forever()
