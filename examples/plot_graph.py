"""
This example generates random data and plots a graph in the browser.

Run it using Gevent directly using:
    $ python plot_grapg.py

Or with an Gunicorn wrapper:
    $ gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" \
        plot_graph:app
"""


import gevent
import logging
import random

from geventwebsocket.server import WebSocketServer


logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def handle(ws):
    """
    This is the websocket handler function. Note that we can dispatch based on
    path in here, too.
    """

    if ws.path == "/echo":
        while True:
            m = ws.receive()
            if m is None:
                break
            ws.send(m)

    elif ws.path == "/data":
        for i in xrange(10000):
            ws.send("0 %s %s\n" % (i, random.random()))
            gevent.sleep(0.1)


def app(environ, start_response):
    if environ["PATH_INFO"] == "/":
        start_response("200 OK", [("Content-Type", "text/html")])
        return open("plot_graph.html").readlines()
    elif environ["PATH_INFO"] in ("/data", "/echo"):
        handle(environ["wsgi.websocket"])
    else:
        start_response("404 Not Found", [])
        return []


if __name__ == "__main__":
    server = WebSocketServer(('', 8000), app, debug=True)
    server.serve_forever()
