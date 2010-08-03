# -*- coding: utf-8 -
#
# gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" gunicorn_websocket:app

import gevent

# demo app
import os
import random
def app(environ, start_response, ws=None):
    if ws.path == '/echo':
        while True:
            m = ws.wait()
            if m is None:
                break
            ws.send(m)

    elif ws.path == '/data':
        for i in xrange(10000):
            ws.send("0 %s %s\n" % (i, random.random()))
            gevent.sleep(1)
