================
gevent-websocket
================

`gevent-websocket`_ is a websocket library for the gevent_ networking library
written written and maintained by `Jeffrey Gelens`_ It is licensed under the BSD license.

Installation
------------

Install Python 2.5 or newer and Gevent and its dependencies. The latest release
can be download from PyPi_ or by cloning the repository_ and running::

    $ python setup.py install

The easiest way to install gevent-websocket is directly from PyPi_ using pip or
setuptools by running the commands below::

    $ pip install gevent-websocket

or::

    $ easy_install gevent-websocket

This also installs the dependencies automatically.


Usage
-----

Gevent Server
^^^^^^^^^^^^^

At the moment gevent-websocket has one handler based on the Pywsgi gevent
Hook up the WebSocketHandler to the Pywsgi Server by setting the `handler_class`
when creating the server instance.

::

    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler

    server = pywsgi.WSGIServer(("", 8000), websocket_app,
        handler_class=WebSocketHandler)
    server.serve_forever()

The handler enhances your WSGI app with a Websocket environment variable when the
browser requests a Websocket connection.

::

    def websocket_app(environ, start_response):
        if environ["PATH_INFO"] == '/echo':
            ws = environ["wsgi.websocket"]
            message = ws.receive()
            ws.send(message)

Gunicorn Server
^^^^^^^^^^^^^^^

Using Gunicorn it is even more easy to start a server. Only the
`websocket_app` from the previous example is required to start the server.
Start Gunicorn using the following command and worker class to enable Websocket
funtionality for the application.

::

    gunicorn -k "geventwebsocket.gunicorn.workers.GeventWebSocketWorker" wsgi:websocket_app

Backwards incompatible changes
------------------------------

- The `wait()` method was renamed to `receive()`.

.. _gevent-websocket: http://www.bitbucket.org/Jeffrey/gevent-websocket/
.. _gevent: http://www.gevent.org/
.. _Jeffrey Gelens: http://www.gelens.org/
.. _PyPi: http://pypi.python.org/pypi/gevent-websocket/
.. _repository: http://www.bitbucket.org/Jeffrey/gevent-websocket/
