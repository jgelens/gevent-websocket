"""
This example generates random data and plots a graph in the browser.

Run it using Gevent directly using:
    $ python plot_grapg.py

Or with an Gunicorn wrapper:
    $ gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" \
        plot_graph:app
"""


import gevent
import random

from geventwebsocket.server import WebSocketServer
from geventwebsocket.resource import WebSocketApplication, Resource


class PlotApplication(WebSocketApplication):
    def on_open(self):
        for i in xrange(10000):
            self.ws.send("0 %s %s\n" % (i, random.random()))
            gevent.sleep(0.1)


def static_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return open("plot_graph.html").readlines()


if __name__ == "__main__":
    resource = Resource(apps={
        '/': static_wsgi_app,
        '/data': PlotApplication
    })
    server = WebSocketServer(('', 8000), resource, debug=True)
    server.serve_forever()
