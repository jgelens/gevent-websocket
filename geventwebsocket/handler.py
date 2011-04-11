import re
import struct
from hashlib import md5
from socket import error

from gevent.pywsgi import WSGIHandler
from geventwebsocket import WebSocket


class WebSocketError(error):
    pass


class BadRequest(WebSocketError):
    """
    This error will be raised by meth:`do_handshake` when encountering an invalid request.
    If left unhandled, it will cause :class:`WebSocketHandler` to log the error and to issue 400 reply.
    It will also be raised by :meth:`connect` if remote server has replied with 4xx error.
    """


class WebSocketHandler(WSGIHandler):
    """ Automatically upgrades the connection to websockets. """
    def __init__(self, *args, **kwargs):
        self.allowed_paths = []

        for expression in kwargs.pop('allowed_paths', []):
            if isinstance(expression, basestring):
                self.allowed_paths.append(re.compile(expression))
            else:
                self.allowed_paths.append(expression)

        super(WebSocketHandler, self).__init__(*args, **kwargs)

    def run_application(self):
        if self.websocket:
            return self.application(self.environ, self.start_response)
        else:
            return super(WebSocketHandler, self).run_application()

    def handle_one_response(self):
        # TODO: refactor to run under run_application
        # In case the client doesn't want to initialize a WebSocket connection
        # we will proceed with the default PyWSGI functionality.
        if self.environ.get("HTTP_CONNECTION") != "Upgrade" or \
           self.environ.get("HTTP_UPGRADE") != "WebSocket" or \
           not self.environ.get("HTTP_ORIGIN") or \
           not self.accept_upgrade():
            return super(WebSocketHandler, self).handle_one_response()

        self.websocket = WebSocket(self.socket, self.rfile, self.environ)
        self.environ['wsgi.websocket'] = self.websocket

        headers = [
            ("Upgrade", "WebSocket"),
            ("Connection", "Upgrade"),
        ]

        # Detect the Websocket protocol
        if "HTTP_SEC_WEBSOCKET_KEY1" in self.environ:
            version = 76
        else:
            version = 75

        if version == 75:
            headers.extend([
                ("WebSocket-Origin", self.websocket.origin),
                ("WebSocket-Protocol", self.websocket.protocol),
                ("WebSocket-Location", "ws://" + self.environ.get('HTTP_HOST') + self.websocket.path),
            ])
            self.start_response("101 Web Socket Protocol Handshake", headers)
        elif version == 76:
            challenge = self._get_challenge()
            headers.extend([
                ("Sec-WebSocket-Origin", self.websocket.origin),
                ("Sec-WebSocket-Protocol", self.websocket.protocol),
                ("Sec-WebSocket-Location", "ws://" + self.environ.get('HTTP_HOST') + self.websocket.path),
            ])

            self.start_response("101 Web Socket Protocol Handshake", headers)
            self.write(challenge)
        else:
            raise Exception("WebSocket version not supported")

        return self.run_application()

    def accept_upgrade(self):
        """
        Returns True if request is allowed to be upgraded.
        If self.allowed_paths is non-empty, self.environ['PATH_INFO'] will
        be matched against each of the regular expressions.
        """

        if self.allowed_paths:
            path_info = self.environ.get('PATH_INFO', '')

            for regexps in self.allowed_paths:
                return regexps.match(path_info)
        else:
            return True

    def write(self, data):
        if self.websocket:
            self.socket.sendall(data)
        else:
            super(WebSocketHandler, self).write(data)

    def start_response(self, status, headers, exc_info=None):
        if self.websocket_connection:
            self.status = status

            towrite = []
            towrite.append('%s %s\r\n' % (self.request_version, self.status))

            for header in headers:
                towrite.append("%s: %s\r\n" % header)

            towrite.append("\r\n")
            self.socket.sendall(towrite)
            self.headers_sent = True
        else:
            super(WebSocketHandler, self).start_response(status, headers, exc_info)

    def _get_key_value(self, key_value):
        key_number = int(re.sub("\\D", "", key_value))
        spaces = re.subn(" ", "", key_value)[1]

        if key_number % spaces != 0:
            raise WebSocketHandler("key_number %d is not an intergral multiple of"
                                 " spaces %d" % (key_number, spaces))

        return key_number / spaces

    def _get_challenge(self):
        key1 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY1')
        key2 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY2')

        if not key1:
            raise BadRequest("SEC-WEBSOCKET-KEY1 header is missing")
        if not key2:
            raise BadRequest("SEC-WEBSOCKET-KEY2 header is missing")

        part1 = self._get_key_value(self.environ['HTTP_SEC_WEBSOCKET_KEY1'])
        part2 = self._get_key_value(self.environ['HTTP_SEC_WEBSOCKET_KEY2'])

        # This request should have 8 bytes of data in the body
        key3 = self.rfile.read(8)

        return md5(struct.pack("!II", part1, part2) + key3).digest()

    def wait(self):
        return self.websocket.wait()

    def send(self, message):
        return self.websocket.send(message)
