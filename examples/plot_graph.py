from __future__ import print_function

"""
This example generates random data and plots a graph in the browser.

Run it using Gevent directly using:
    $ python plot_graph.py

Or with an Gunicorn wrapper:
    $ gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" \
        plot_graph:resource
"""

import gevent
import random

from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from geventwebsocket._compat import range_type


class PlotApplication(WebSocketApplication):
    def on_open(self):
        for i in range_type(10000):
            self.ws.send("0 %s %s\n" % (i, random.random()))
            gevent.sleep(0.1)

    def on_close(self, reason):
        print("Connection Closed!!!", reason)


def static_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return open("plot_graph.html").readlines()


resource = Resource([
    ('/', static_wsgi_app),
    ('/data', PlotApplication)
])

if __name__ == "__main__":
    server = WebSocketServer(('', 8000), resource, debug=True)
    server.serve_forever()
