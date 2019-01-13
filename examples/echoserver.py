from __future__ import print_function

import os
import logging
import geventwebsocket

from geventwebsocket.server import WebSocketServer

logging.basicConfig(level=logging.DEBUG)

def echo_app(environ, start_response):
    websocket = environ.get("wsgi.websocket")

    if websocket is None:
        return http_handler(environ, start_response)
    try:
        while True:
            message = websocket.receive()
            websocket.send(message)
        websocket.close()
    except geventwebsocket.WebSocketError as ex:
        print("{0}: {1}".format(ex.__class__.__name__, ex))


def http_handler(environ, start_response):
    if environ["PATH_INFO"].strip("/") == "version":
        start_response("200 OK", [])
        return [agent]

    else:
        start_response("400 Bad Request", [])

        return ["WebSocket connection is expected here."]


path = os.path.dirname(geventwebsocket.__file__)
agent = bytearray("gevent-websocket/%s" % (geventwebsocket.get_version()),
                  'latin-1')

print("Running %s from %s" % (agent, path))
WebSocketServer(("", 8000), echo_app, debug=False).serve_forever()
