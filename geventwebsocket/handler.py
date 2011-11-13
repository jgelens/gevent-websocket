import base64
import re
import struct
from hashlib import md5, sha1
from base64 import b64encode, b64decode

from gevent.pywsgi import WSGIHandler
from geventwebsocket import WebSocketVersion7, WebSocketLegacy



class HandShakeError(ValueError):
    """ Hand shake challenge can't be parsed """
    pass


class WebSocketHandler(WSGIHandler):
    """ Automatically upgrades the connection to websockets. """

    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    SUPPORTED_VERSIONS = (7,8)

    def __init__(self, *args, **kwargs):
        self.websocket_connection = False
        self.allowed_paths = []

        for expression in kwargs.pop('allowed_paths', []):
            if isinstance(expression, basestring):
                self.allowed_paths.append(re.compile(expression))
            else:
                self.allowed_paths.append(expression)

        super(WebSocketHandler, self).__init__(*args, **kwargs)

    def handle_one_response(self, call_wsgi_app=True):
        if self.environ.get("HTTP_ORIGIN"):
            self._handle_one_legacy_response()
        elif self.environ.get("HTTP_SEC_WEBSOCKET_VERSION"):
            version = int(self.environ.get("HTTP_SEC_WEBSOCKET_VERSION"))
            if version is 7:
                if not self._handle_one_version7_response():
                    return
            else:
                return
        else:
            # not a valid websocket request
            return super(WebSocketHandler, self).handle_one_response()

        if call_wsgi_app:
            return self.application(self.environ, self.start_response)
        else:
            return

    def _close_connection(self, reason=None):
        # based on gevent/pywsgi.py
        # see http://pypi.python.org/pypi/gevent#downloads

        if reason:
            print "Closing the connection because %s!" % reason
        if self.socket is not None:
            try:
                self.socket._sock.close()
                self.socket.close()
            except socket.error:
                pass

    def _handle_one_version7_response(self):
        environ = self.environ

        protocol, version = self.request_version.split("/")
        key = environ.get("HTTP_SEC_WEBSOCKET_KEY")

        # check client handshake for validity
        if not environ.get("REQUEST_METHOD") == "GET":
            # 5.2.1 (1)
            self._close_connection()
            return False
        elif not protocol == "HTTP":
            # 5.2.1 (1)
            self._close_connection()
            return False
        elif float(version) < 1.1:
            # 5.2.1 (1)
            self._close_connection()
            return False
        # XXX: nobody seems to set SERVER_NAME correctly. check the spec
        #elif not environ.get("HTTP_HOST") == environ.get("SERVER_NAME"):
            # 5.2.1 (2)
            #self._close_connection()
            #return False
        elif not key:
            # 5.2.1 (3)
            self._close_connection()
            return False
        elif len(base64.b64decode(key)) != 16:
            # 5.2.1 (3)
            self._close_connection()
            return False

        #TODO: compare Sec-WebSocket-Origin against self.allowed_paths

        self.websocket_connection = True
        self.websocket = WebSocketVersion7(self.socket, self.rfile, self.environ)
        self.environ['wsgi.websocket'] = self.websocket

        headers = [
            ("Upgrade", "websocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Accept", base64.b64encode(sha1(key + self.GUID).digest())),
        ]
        self.start_response("101 Switching Protocols", headers)
        return True

    def _handle_one_legacy_response(self):
        # In case the client doesn't want to initialize a WebSocket connection
        # we will proceed with the default PyWSGI functionality.
        print self.environ.get("HTTP_CONNECTION", "").lower().split(",")

        if "upgrade" in self.environ.get("HTTP_CONNECTION", "").lower(). \
             replace(" ", "").split(",") and \
             "websocket" in self.environ.get("HTTP_UPGRADE").lower() and \
             self.upgrade_allowed():
            self.websocket_connection = True
        else:
            print "NORMAL"
            from pprint import pprint
            pprint(self.environ)
            return super(WebSocketHandler, self).handle_one_response()

        self.init_websocket()
        self.environ['wsgi.websocket'] = self.websocket

        # Detect the Websocket protocol
        if "HTTP_SEC_WEBSOCKET_KEY1" in self.environ:
            version = 76
        else:
            version = 75

        if version == 75:
            headers = [
                ("Upgrade", "WebSocket"),
                ("Connection", "Upgrade"),
                ("WebSocket-Origin", self.websocket.origin),
                ("WebSocket-Protocol", self.websocket.protocol),
                ("WebSocket-Location", "ws://" + self.environ.get('HTTP_HOST') + self.websocket.path),
            ]
            self.start_response("101 Web Socket Protocol Handshake", headers)
        elif version == 76:
            challenge = self._get_challenge()
            headers = [
                ("Upgrade", "WebSocket"),
                ("Connection", "Upgrade"),
                ("Sec-WebSocket-Origin", self.websocket.origin),
                ("Sec-WebSocket-Protocol", self.websocket.protocol),
                ("Sec-WebSocket-Location", "ws://" + self.environ.get('HTTP_HOST') + self.websocket.path),
            ]

            self.start_response("101 Web Socket Protocol Handshake", headers)
            self.write(challenge)
        else:
            raise Exception("Version not supported")

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
        if self.websocket_connection:
            if data:
                self.socket.sendall(data)
            else:
                raise Exception("No data to send")
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
            msg = ''.join(towrite)
            self.socket.sendall(msg)
            self.headers_sent = True
        else:
            super(WebSocketHandler, self).start_response(status, headers, exc_info)

    def _get_key_value(self, key_value):
        key_number = int(re.sub("\\D", "", key_value))
        spaces = re.subn(" ", "", key_value)[1]

        if key_number % spaces != 0:
            raise HandShakeError("key_number %d is not an intergral multiple of"
                                 " spaces %d" % (key_number, spaces))

        return key_number / spaces

    def _get_challenge_hybi00(self):
        key1 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY1')
        key2 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY2')

        if not (key1 and key2):
            message = "Client using old/invalid protocol implementation"
            headers = [("Content-Length", str(len(message))),]
            self.start_response("400 Bad Request", headers)
            self.write(message)
            self.close_connection = True
            return

        part1 = self._get_key_value(self.environ['HTTP_SEC_WEBSOCKET_KEY1'])
        part2 = self._get_key_value(self.environ['HTTP_SEC_WEBSOCKET_KEY2'])

        # This request should have 8 bytes of data in the body
        key3 = self.rfile.read(8)

        challenge = ""
        challenge += struct.pack("!I", part1)
        challenge += struct.pack("!I", part2)
        challenge += key3

        return md5(challenge).digest()

    def _get_challenge_hybi06(self):
        key = self.environ.get("HTTP_SEC_WEBSOCKET_KEY")
        return b64encode(sha1(key + MAGIC_STRING).digest())

    def wait(self):
        return self.websocket.wait()

    def send(self, message):
        return self.websocket.send(message)
