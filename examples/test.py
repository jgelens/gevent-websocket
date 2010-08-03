from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi
import gevent


# demo app
import os
import random
def handle(environ, start_response, ws):
    """  This is the websocket handler function.  Note that we
    can dispatch based on path in here, too."""
    if ws.path == '/echo':
        while True:
            m = ws.wait()
            if m is None:
                break
            ws.send(m)

    elif ws.path == '/data':
        for i in xrange(10000):
            ws.send("0 %s %s\n" % (i, random.random()))
            #print "0 %s %s\n" % (i, random.random())
            gevent.sleep(0.1)

server = pywsgi.WSGIServer(('0.0.0.0', 9999), handle,
        handler_class=WebSocketHandler)
server.serve_forever()
