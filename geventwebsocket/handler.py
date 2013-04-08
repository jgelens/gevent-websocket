import base64
import hashlib

from gevent.pywsgi import WSGIHandler
from .websocket import WebSocket, Stream
from .logging import create_logger


class WebSocketHandler(WSGIHandler):
    """
    Automatically upgrades the connection to a websocket.

    To prevent the WebSocketHandler to call the underlying WSGI application,
    but only setup the WebSocket negotiations, do:

      mywebsockethandler.prevent_wsgi_call = True

    before calling run_application().  This is useful if you want to do more
    things before calling the app, and want to off-load the WebSocket
    negotiations to this library.  Socket.IO needs this for example, to send
    the 'ack' before yielding the control to your WSGI app.
    """

    SUPPORTED_VERSIONS = ('13', '8', '7')
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def run_websocket(self):
        """
        Called when a websocket has been created successfully.
        """
        if hasattr(self, 'prevent_wsgi_call') and self.prevent_wsgi_call:
            return

        # Since we're now a websocket connection, we don't care what the
        # application actually responds with for the http response
        try:
            self.application(self.environ, lambda s, h: [])
        finally:
            self.websocket.close()

    def run_application(self):
        self.logger.debug("Application started")
        self.result = self.upgrade_websocket()

        if hasattr(self, 'websocket'):
            if self.status and not self.headers_sent:
                self.write('')

            self.run_websocket()
        else:
            if self.status:
                # A status was set, likely an error so just send the response
                if not self.result:
                    self.result = []

                self.process_result()
                return

            # This handler did not handle the request, so defer it to the
            # underlying application object
            return super(WebSocketHandler, self).run_application()

    def upgrade_websocket(self):
        """
        Attempt to upgrade the current environ into a websocket enabled
        connection. If successful, the environ dict with be updated with two
        new entries, `wsgi.websocket` and `wsgi.websocket_version`.

        :returns: Whether the upgrade was successful.
        """

        # Some basic sanity checks first

        self.logger.debug("Validating WebSocket request")

        if self.environ.get('REQUEST_METHOD', '') != 'GET':
            self.start_response('400 Bad Request', [])
            self.logger.warning("No request method in headers")

            return ['Unknown request method']

        if self.request_version != 'HTTP/1.1':
            self.start_response('402 Bad Request', [])
            self.logger.warning("Bad server protocol in headers")

            return ['Bad protocol version']

        upgrade = self.environ.get('HTTP_UPGRADE', '').lower()

        if upgrade == 'websocket':
            connection = self.environ.get('HTTP_CONNECTION', '').lower()

            if 'upgrade' not in connection:
                # This is not a websocket request, so we must not handle it
                self.logger.warning("Client didn't ask for a connection "
                                    "upgrade")
                return
        else:
            # This is not a websocket request, so we must not handle it
            return

        if self.environ.get('HTTP_SEC_WEBSOCKET_VERSION'):
            return self.upgrade_connection()
        else:
            self.logger.warning("No protocol defined")
            self.start_response('426 Upgrade Required', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))])

            return ['No Websocket protocol version defined']

    def upgrade_connection(self):
        """
        Validate and 'upgrade' the HTTP request to a WebSocket request.

        If an upgrade succeeded then then handler will have `start_response`
        with a status of `101`, the environ will also be updated with
        `wsgi.websocket` and `wsgi.websocket_version` keys.

        :param environ: The WSGI environ dict.
        :param start_response: The callable used to start the response.
        :param stream: File like object that will be read from/written to by
            the underlying WebSocket object, if created.
        :return: The WSGI response iterator is something went awry.
        """

        self.logger.debug("Attempting to upgrade connection")

        version = self.environ.get("HTTP_SEC_WEBSOCKET_VERSION")

        if version not in self.SUPPORTED_VERSIONS:
            msg = "Unsupported WebSocket Version: {0}".format(version)

            self.logger.warning(msg)
            self.start_response('400 Bad Request', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))
            ])

            return [msg]

        key = self.environ.get("HTTP_SEC_WEBSOCKET_KEY", '').strip()

        if not key:
            # 5.2.1 (3)
            msg = "Sec-WebSocket-Key header is missing/empty"

            self.logger.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        try:
            key_len = len(base64.b64decode(key))
        except TypeError:
            msg = "Invalid key: {0}".format(key)

            self.logger.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        if key_len != 16:
            # 5.2.1 (3)
            msg = "Invalid key: {0}".format(key)

            self.logger.warning(msg)
            self.start_response('400 Bad Request', [])

            return [msg]

        self.websocket = WebSocket(self.environ, Stream(self))

        self.environ.update({
            'wsgi.websocket_version': version,
            'wsgi.websocket': self.websocket
        })

        headers = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", base64.b64encode(
                hashlib.sha1(key + self.GUID).digest())),
        ]

        self.logger.debug("WebSocket request accepted, switching protocols")
        self.start_response("101 Switching Protocols", headers)

    @property
    def logger(self):
        if not hasattr(self.server, 'logger'):
            self.server.logger = create_logger(__name__)

        return self.server.logger



#class MessageHandler(object):
#    def __init__(self, environ, interfaces):
#        self.ws = environ['wsgi.websocket']
#        self.interfaces = interfaces
#
#        if self.ws.path in interfaces.keys():
#            self.active_interface = interfaces[self.ws.path]
#        else:
#            raise Exception("no interface found")
#
#        self.on_open()
#        self._handle()
#
#    def _handle(self):
#        while True:
#            message = self.ws.receive()
#
#            if message is None:
#                self.active_interface.on_close()
#                break
#            else:
#                self.active_interface.on_message(message)
