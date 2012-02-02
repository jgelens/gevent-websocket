import base64
import re
import struct
from hashlib import md5, sha1
from socket import error as socket_error
from urllib import quote

from gevent.pywsgi import WSGIHandler
from geventwebsocket.websocket import WebSocketHybi, WebSocketHixie


class WebSocketHandler(WSGIHandler):
    """ Automatically upgrades the connection to websockets. """

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    SUPPORTED_VERSIONS = ('13', '8', '7')

    def handle_one_response(self):
        self.pre_start()
        environ = self.environ
        upgrade = environ.get('HTTP_UPGRADE', '').lower()

        if upgrade == 'websocket':
            connection = environ.get('HTTP_CONNECTION', '').lower()
            if 'upgrade' in connection:
                return self._handle_websocket()
        return super(WebSocketHandler, self).handle_one_response()

    def pre_start(self):
        pass

    def _handle_websocket(self):
        environ = self.environ

        try:
            if environ.get("HTTP_SEC_WEBSOCKET_VERSION"):
                self.close_connection = True
                result = self._handle_hybi()
            elif environ.get("HTTP_ORIGIN"):
                self.close_connection = True
                result = self._handle_hixie()

            self.result = []
            if not result:
                return

            self.application(environ, None)
            return []
        finally:
            self.log_request()

    def _handle_hybi(self):
        environ = self.environ
        version = environ.get("HTTP_SEC_WEBSOCKET_VERSION")

        environ['wsgi.websocket_version'] = 'hybi-%s' % version

        if version not in self.SUPPORTED_VERSIONS:
            self.log_error('400: Unsupported Version: %r', version)
            self.respond(
                '400 Unsupported Version',
                [('Sec-WebSocket-Version', '13, 8, 7')]
            )
            return

        protocol, version = self.request_version.split("/")
        key = environ.get("HTTP_SEC_WEBSOCKET_KEY")

        # check client handshake for validity
        if not environ.get("REQUEST_METHOD") == "GET":
            # 5.2.1 (1)
            self.respond('400 Bad Request')
            return
        elif not protocol == "HTTP":
            # 5.2.1 (1)
            self.respond('400 Bad Request')
            return
        elif float(version) < 1.1:
            # 5.2.1 (1)
            self.respond('400 Bad Request')
            return
        # XXX: nobody seems to set SERVER_NAME correctly. check the spec
        #elif not environ.get("HTTP_HOST") == environ.get("SERVER_NAME"):
            # 5.2.1 (2)
            #self.respond('400 Bad Request')
            #return
        elif not key:
            # 5.2.1 (3)
            self.log_error('400: HTTP_SEC_WEBSOCKET_KEY is missing from request')
            self.respond('400 Bad Request')
            return
        elif len(base64.b64decode(key)) != 16:
            # 5.2.1 (3)
            self.log_error('400: Invalid key: %r', key)
            self.respond('400 Bad Request')
            return

        self.websocket = WebSocketHybi(self.socket, environ)
        environ['wsgi.websocket'] = self.websocket

        headers = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + self.GUID).digest())),
        ]
        self._send_reply("101 Switching Protocols", headers)
        return True

    def _handle_hixie(self):
        environ = self.environ
        assert "upgrade" in self.environ.get("HTTP_CONNECTION", "").lower()

        self.websocket = WebSocketHixie(self.socket, environ)
        environ['wsgi.websocket'] = self.websocket

        key1 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY1')
        key2 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY2')

        if key1 is not None:
            environ['wsgi.websocket_version'] = 'hixie-76'
            if not key1:
                self.log_error("400: SEC-WEBSOCKET-KEY1 header is empty")
                self.respond('400 Bad Request')
                return
            if not key2:
                self.log_error("400: SEC-WEBSOCKET-KEY2 header is missing or empty")
                self.respond('400 Bad Request')
                return

            part1 = self._get_key_value(key1)
            part2 = self._get_key_value(key2)
            if part1 is None or part2 is None:
                self.respond('400 Bad Request')
                return

            headers = [
                ("Upgrade", "WebSocket"),
                ("Connection", "Upgrade"),
                ("Sec-WebSocket-Location", reconstruct_url(environ)),
            ]
            if self.websocket.protocol is not None:
                headers.append(("Sec-WebSocket-Protocol", self.websocket.protocol))
            if self.websocket.origin:
                headers.append(("Sec-WebSocket-Origin", self.websocket.origin))

            self._send_reply("101 Web Socket Protocol Handshake", headers)

            # This request should have 8 bytes of data in the body
            key3 = self.rfile.read(8)

            challenge = md5(struct.pack("!II", part1, part2) + key3).digest()

            self.socket.sendall(challenge)
            return True
        else:
            environ['wsgi.websocket_version'] = 'hixie-75'
            headers = [
                ("Upgrade", "WebSocket"),
                ("Connection", "Upgrade"),
                ("WebSocket-Location", reconstruct_url(environ)),
            ]

            if self.websocket.protocol is not None:
                headers.append(("WebSocket-Protocol", self.websocket.protocol))
            if self.websocket.origin:
                headers.append(("WebSocket-Origin", self.websocket.origin))

            self._send_reply("101 Web Socket Protocol Handshake", headers)

    def _send_reply(self, status, headers):
        self.status = status

        towrite = []
        towrite.append('%s %s\r\n' % (self.request_version, self.status))

        for header in headers:
            towrite.append("%s: %s\r\n" % header)

        towrite.append("\r\n")
        msg = ''.join(towrite)
        self.socket.sendall(msg)
        self.headers_sent = True

    def respond(self, status, headers=[]):
        self.close_connection = True
        self._send_reply(status, headers)

        if self.socket is not None:
            try:
                self.socket._sock.close()
                self.socket.close()
            except socket_error:
                pass

    def _get_key_value(self, key_value):
        key_number = int(re.sub("\\D", "", key_value))
        spaces = re.subn(" ", "", key_value)[1]

        if key_number % spaces != 0:
            self.log_error("key_number %d is not an intergral multiple of spaces %d", key_number, spaces)
        else:
            return key_number / spaces


def reconstruct_url(environ):
    secure = environ['wsgi.url_scheme'] == 'https'
    if secure:
        url = 'wss://'
    else:
        url = 'ws://'

    if environ.get('HTTP_HOST'):
        url += environ['HTTP_HOST']
    else:
        url += environ['SERVER_NAME']

        if secure:
            if environ['SERVER_PORT'] != '443':
                url += ':' + environ['SERVER_PORT']
        else:
            if environ['SERVER_PORT'] != '80':
                url += ':' + environ['SERVER_PORT']

    url += quote(environ.get('SCRIPT_NAME', ''))
    url += quote(environ.get('PATH_INFO', ''))

    if environ.get('QUERY_STRING'):
        url += '?' + environ['QUERY_STRING']

    return url
