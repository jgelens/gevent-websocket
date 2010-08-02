import re
import struct
import time
import traceback
import sys
from hashlib import md5
from gevent.pywsgi import WSGIHandler
from geventwebsocket import WebSocket

class WebSocketHandler(WSGIHandler):
    def handle_one_response(self):
        self.time_start = time.time()
        self.status = None
        self.response_length = 0

        if self.environ.get("HTTP_CONNECTION") != "Upgrade" or \
           self.environ.get("HTTP_UPGRADE") != "WebSocket" or \
           not self.environ.get("HTTP_ORIGIN"):
            message = "Websocket connection expected"
            headers = [("Content-Length", str(len(message))),]
            self.start_response("HTTP/1.1 400 Bad Request", headers, message)
            self.close_connection = True
            return

        ws = WebSocket(self.rfile, self.wfile, self.socket, self.environ)
        challenge = self._get_challenge()

        headers = [
            ("Upgrade", "WebSocket"),
            ("Connection", "Upgrade"),
            ("Sec-WebSocket-Origin", ws.origin),
            ("Sec-WebSocket-Protocol", ws.protocol),
            ("Sec-WebSocket-Location", "ws://" + self.environ.get('HTTP_HOST') + ws.path),
        ]

        self.start_response(
            "HTTP/1.1 101 Web Socket Protocol Handshake", headers, challenge
        )

        try:
            self.application(self.environ, self.start_response, ws)
        except Exception:
            traceback.print_exc()
            sys.exc_clear()
            try:
                args = (getattr(self, 'server', ''),
                        getattr(self, 'requestline', ''),
                        getattr(self, 'client_address', ''),
                        getattr(self, 'application', ''))
                msg = '%s: Failed to handle request:\n  request = %s from %s\n  application = %s\n\n' % args
                sys.stderr.write(msg)
            except Exception:
                sys.exc_clear()
        finally:
            self.wsgi_input._discard()
            self.time_finish = time.time()
            self.log_request()

    def start_response(self, status, headers, body=None):
        towrite = [status]
        for header in headers:
            towrite.append(": ".join(header))

        if body is not None:
            towrite.append("")
            towrite.append(body)

        self.wfile.write("\r\n".join(towrite))

    def _get_key_value(self, key_value):
        key_number = int(re.sub("\\D", "", key_value))
        spaces = re.subn(" ", "", key_value)[1]

        if key_number % spaces != 0:
            raise HandShakeError("key_number %d is not an intergral multiple of"
                                 " spaces %d" % (key_number, spaces))

        return key_number / spaces

    def _get_challenge(self):
        key1 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY1')
        key2 = self.environ.get('HTTP_SEC_WEBSOCKET_KEY2')
        if not (key1 and key2):
            message = "Client using old protocol implementation"
            headers = [("Content-Length", str(len(message))),]
            self.start_response("HTTP/1.1 400 Bad Request", headers, message)
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
