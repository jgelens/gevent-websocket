gevent-websocket
================

gevent-websocket is a `WebSocket`_ library for the gevent_ networking library
written written and maintained by `Jeffrey Gelens`_ It is licensed under the BSD license.

::

    from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

    class EchoApplication(WebSocketApplication):
        def on_message(self, message):
            self.ws.send(message)

    WebSocketServer(
        ('', 8000),
        Resource({'/': EchoApplication})
    )


Add WebSockets to your WSGI application
=======================================

It isn't necessary to use the build-in `WebSocketServer` to start using
WebSockets. WebSockers can be added to existing applications very easy by
making the non-standard `wsgi.websocket` variable available in the WSGI
environment. An example using `Flask <http://flask.pocoo.org>`_ follows::

    from geventwebsocket import WebSocketServer, WebSocketError
    from flask import Flask, request, render_template

    app = Flask(__name__)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api')
    def api():
        ws = request.environ.get('wsgi.websocket')

        if not ws:
            abort(400, "Expected WebSocket request")

        while True:
            try:
                message = ws.receive()
                ws.send("Your message was: {}".format(message))
            except WebSocketError:
                # Possibility to execute code when connection is closed
                break

    if __name__ == '__main__':
        server = WebSocketServer(("", 8000), app)
        server.serve_forever()

Also the browser Javascript application can be very simple::

    <!DOCTYPE html>
    <html>
    <head>
      <script>
        var ws = new WebSocket("ws://localhost:8000/api");

        ws.onopen = function() {
            ws.send("Hello, world");
        };
        ws.onmessage = function (event) {
            alert(event.data);
        };
      </script>
    </head>
    </html>

Features
========

- Framework for WebSocket servers and WebSocket subprotocols
- Implementation of RFC6455_ and Hybi-10+
- gevent_ based: high performance, asynchronous
- standards conformance (100% passes the `Autobahn Websocket Testsuite`_)

Installation
============

Distribute & Pip
----------------

Installing gevent-websocket is simple with `pip <http://www.pip-installer.org>`_::

    $ pip install gevent-websocket

Get the Code
------------

Requests is being developed on BitBucket.

You can clone the repsistory::

    hg clone https://www.bitbucket.org/Jeffrey/gevent-websocket

or download the tarball::

    curl -LO https://bitbucket.org/Jeffrey/gevent-websocket/TODO

Once you have a copy, you can either embed it in your application, or installed
it on your system with::

    $ python setup.py install


API
===

.. module:: geventwebsocket

Main classes
------------

.. autoclass:: geventwebsocket.server.WebSocketServer
   :inherited-members:

.. autoclass:: geventwebsocket.resource.WebSocketApplication
   :inherited-members:

.. autoclass:: geventwebsocket.resource.Resource
   :inherited-members:

Exceptions
----------

.. module:: geventwebsocket.exceptions

.. autoexception:: WebSocketError


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _Autobahn Websocket Testsuite: http://autobahn.ws/testsuite
.. _RFC6455: http://datatracker.ietf.org/doc/rfc6455/?include_text=1
.. _WebSocket: http://www.websocket.org/aboutwebsocket.html
.. _repository: http://www.bitbucket.org/Jeffrey/gevent-websocket/
.. _PyPi: http://pypi.python.org/pypi/gevent-websocket/
.. _gevent-websocket: http://www.bitbucket.org/Jeffrey/gevent-websocket/
.. _gevent: http://www.gevent.org
.. _Jeffrey Gelens: http://www.noppo.pro
