# Websocket tests by Jeffrey Gelens, Copyright 2010, Noppo.pro
# Socket related functions by:
#
# @author Donovan Preston
#
# Copyright (c) 2007, Linden Research, Inc.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
from gevent import monkey
monkey.patch_all(thread=False)

import binascii
import base64
import struct
import sys
import greentest
import gevent
import gevent.local
from gevent import socket
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocketVersion7

CONTENT_LENGTH = 'Content-Length'
CONN_ABORTED_ERRORS = []
DEBUG = '-v' in sys.argv

try:
    from errno import WSAECONNABORTED
    CONN_ABORTED_ERRORS.append(WSAECONNABORTED)
except ImportError:
    pass


class ConnectionClosed(Exception):
    pass


def read_headers(fd):
    response_line = fd.readline()
    if not response_line:
        raise ConnectionClosed
    headers = {}
    while True:
        line = fd.readline().strip()
        if not line:
            break
        try:
            key, value = line.split(': ', 1)
        except:
            print 'Failed to split: %r' % (line, )
            raise
        assert key.lower() not in [x.lower() for x in headers.keys()], 'Header %r:%r sent more than once: %r' % (key, value, headers)
        headers[key] = value
    return response_line, headers


def iread_chunks(fd):
    while True:
        line = fd.readline()
        chunk_size = line.strip()
        try:
            chunk_size = int(chunk_size, 16)
        except:
            print 'Failed to parse chunk size: %r' % line
            raise
        if chunk_size == 0:
            crlf = fd.read(2)
            assert crlf == '\r\n', repr(crlf)
            break
        data = fd.read(chunk_size)
        yield data
        crlf = fd.read(2)
        assert crlf == '\r\n', repr(crlf)


class Response(object):

    def __init__(self, status_line, headers, body=None, chunks=None):
        self.status_line = status_line
        self.headers = headers
        self.body = body
        self.chunks = chunks
        try:
            version, code, self.reason = status_line[:-2].split(' ', 2)
        except Exception:
            print 'Error: %r' % status_line
            raise
        self.code = int(code)
        HTTP, self.version = version.split('/')
        assert HTTP == 'HTTP', repr(HTTP)
        assert self.version in ('1.0', '1.1'), repr(self.version)

    def __iter__(self):
        yield self.status_line
        yield self.headers
        yield self.body

    def __str__(self):
        args = (self.__class__.__name__, self.status_line, self.headers, self.body, self.chunks)
        return '<%s status_line=%r headers=%r body=%r chunks=%r>' % args

    def assertCode(self, code):
        if hasattr(code, '__contains__'):
            assert self.code in code, 'Unexpected code: %r (expected %r)\n%s' % (self.code, code, self)
        else:
            assert self.code == code, 'Unexpected code: %r (expected %r)\n%s' % (self.code, code, self)

    def assertReason(self, reason):
        assert self.reason == reason, 'Unexpected reason: %r (expected %r)\n%s' % (self.reason, reason, self)

    def assertVersion(self, version):
        assert self.version == version, 'Unexpected version: %r (expected %r)\n%s' % (self.version, version, self)

    def assertHeader(self, header, value):
        real_value = self.headers.get(header)
        assert real_value == value, \
               'Unexpected header %r: %r (expected %r)\n%s' % (header, real_value, value, self)

    def assertBody(self, body):
        assert self.body == body, \
               'Unexpected body: %r (expected %r)\n%s' % (self.body, body, self)

    @classmethod
    def read(cls, fd, code=200, reason='default', version='1.1', body=None):
        _status_line, headers = read_headers(fd)
        self = cls(_status_line, headers)
        if code is not None:
            self.assertCode(code)
        if reason == 'default':
            reason = {200: 'OK'}.get(code)
        if reason is not None:
            self.assertReason(reason)
        if version is not None:
            self.assertVersion(version)
        if self.code == 100:
            return self
        try:
            if 'chunked' in headers.get('Transfer-Encoding', ''):
                if CONTENT_LENGTH in headers:
                    print "WARNING: server used chunked transfer-encoding despite having Content-Length header (libevent 1.x's bug)"
                self.chunks = list(iread_chunks(fd))
                self.body = ''.join(self.chunks)
            elif CONTENT_LENGTH in headers:
                num = int(headers[CONTENT_LENGTH])
                self.body = fd.read(num)
            #else:
            #    self.body = fd.read(16)
        except:
            print 'Response.read failed to read the body:\n%s' % self
            raise
        if body is not None:
            self.assertBody(body)
        return self

read_http = Response.read


class DebugFileObject(object):

    def __init__(self, obj):
        self.obj = obj

    def read(self, *args):
        result = self.obj.read(*args)
        if DEBUG:
            print repr(result)
        return result

    def readline(self, *args):
        result = self.obj.readline(*args)
        if DEBUG:
            print repr(result)
        return result

    def __getattr__(self, item):
        assert item != 'obj'
        return getattr(self.obj, item)


def makefile(self, mode='r', bufsize=-1):
    return DebugFileObject(socket._fileobject(self.dup(), mode, bufsize))

socket.socket.makefile = makefile

import gevent.coros
class TestCase(greentest.TestCase):
    __timeout__ = 5
    _testlock = gevent.coros.Semaphore(1)

    def get_wsgi_module(self):
        from gevent import pywsgi
        return pywsgi

    def init_server(self, application):
        self.local = gevent.local.local()
        self.local.server = self.get_wsgi_module().WSGIServer(('127.0.0.1', 0),
            application, handler_class=WebSocketHandler)

    def setUp(self):
        application = self.application
        self.init_server(application)
        self.local.server.start()
        self.port = self.local.server.server_port
        greentest.TestCase.setUp(self)

    def tearDown(self):
        greentest.TestCase.tearDown(self)
        timeout = gevent.Timeout.start_new(0.5)
        try:
            self.local.server.stop()
        finally:
            timeout.cancel()

    def connect(self):
        return socket.create_connection(('127.0.0.1', self.port))

class TestWebSocket(TestCase):
    message = "\x00Hello world\xff"

    def application(self, environ, start_response):
        if environ['PATH_INFO'] == "/echo":
            try:
                ws = environ['wsgi.websocket']
            except KeyError:
                start_response("400 Bad Request", [])
                return []

            while True:
                message = ws.wait()
                if message is None:
                    break
                ws.send(message)

            return []

    def test_basic(self):
        fd = self.connect().makefile(bufsize=1)
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key2: 12998 5 Y3 1  .P00\r\n" \
        "Sec-WebSocket-Protocol: test\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Sec-WebSocket-Key1: 4 @1  46546xW%0l 1 5\r\n" \
        "Origin: http://localhost\r\n\r\n" \
        "^n:ds[4U"

        fd.write(headers)

        response = read_http(fd, code=101, reason="Web Socket Protocol Handshake")
        response.assertHeader("Upgrade", "WebSocket")
        response.assertHeader("Connection", "Upgrade")
        response.assertHeader("Sec-WebSocket-Origin", "http://localhost")
        response.assertHeader("Sec-WebSocket-Location", "ws://localhost/echo")
        response.assertHeader("Sec-WebSocket-Protocol", "test")
        assert fd.read(16) == "8jKS'y:G*Co,Wxa-"

        fd.write(self.message)
        message = fd.read(len(self.message))
        assert message == self.message, \
               'Unexpected message: %r (expected %r)\n%s' % (message, self.message, self)

        fd.close()

    def test_10000_messages(self):
        fd = self.connect().makefile(bufsize=1)
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key2: 12998 5 Y3 1  .P00\r\n" \
        "Sec-WebSocket-Protocol: test\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Sec-WebSocket-Key1: 4 @1  46546xW%0l 1 5\r\n" \
        "Origin: http://localhost\r\n\r\n" \
        "^n:ds[4U"

        fd.write(headers)

        response = read_http(fd, code=101, reason="Web Socket Protocol Handshake")
        response.assertHeader("Upgrade", "WebSocket")
        response.assertHeader("Connection", "Upgrade")
        response.assertHeader("Sec-WebSocket-Origin", "http://localhost")
        response.assertHeader("Sec-WebSocket-Location", "ws://localhost/echo")
        response.assertHeader("Sec-WebSocket-Protocol", "test")
        assert fd.read(16) == "8jKS'y:G*Co,Wxa-"

        for i in xrange(10000):
            fd.write(self.message)
            message = fd.read(len(self.message))

            assert message == self.message, \
                   'Unexpected message: %r (expected %r)\n%s' % (message, self.message, self)


        fd.close()

    def test_badrequest(self):
        fd = self.connect().makefile(bufsize=1)
        fd.write('GET /echo HTTP/1.1\r\nHost: localhost\r\n\r\n')
        read_http(fd, code=400, reason='Bad Request')
        fd.close()

    def test_oldprotocol_version(self):
        fd = self.connect().makefile(bufsize=1)
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Protocol: test\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Sec-WebSocket-Key1: 4 @1  46546xW%0l 1 5\r\n" \
        "Origin: http://localhost\r\n\r\n" \
        "^n:ds[4U"

        fd.write(headers)
        read_http(fd, code=400, reason='Bad Request',
            body='Client using old/invalid protocol implementation')

        fd.close()

    def test_protocol_version75(self):
        fd = self.connect().makefile(bufsize=1)
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Connection: Upgrade\r\n" \
        "WebSocket-Protocol: sample\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Origin: http://example.com\r\n\r\n"

        fd.write(headers)
        response = read_http(fd, code=101, reason="Web Socket Protocol Handshake")

        fd.write(self.message)
        message = fd.read(len(self.message))
        assert message == self.message, \
               'Unexpected message: %r (expected %r)\n%s' % (message, self.message, self)

        fd.close()

class TestWebSocketVersion7(TestCase):

    GOOD_HEADERS = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

    def application(self, environ, start_response):
        if environ['PATH_INFO'] == "/echo":
            try:
                ws = environ['wsgi.websocket']
                self.ws = ws
            except KeyError:
                start_response("400 Bad Request", [])
                return []

            while not ws.websocket_closed:
                gevent.sleep()
            self.close_connection = True
            return None

    def test_bad_handshake_method(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "POST /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd, code=101, reason="Web Socket Protocol Handshake")
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with bad method"
        fd.close()

    def test_bad_handshake_version(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "GET /echo HTTP/1.0\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd)
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with bad version"
        fd.close()

    def test_bad_handshake_host(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: example.com\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd)
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with bad Host"
        fd.close()

    def test_bad_handshake_no_key(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd)
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with no Sec-WebSocket-Key"
        fd.close()

    def test_bad_handshake_short_key(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: " + base64.b64encode('too short') + "\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd)
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with key that is too short"
        fd.close()

    def test_bad_handshake_long_key(self):
        fd = self.connect().makefile(bufsize=1)
        closed = False
        headers = "" \
        "GET /echo HTTP/1.1\r\n" \
        "Host: localhost\r\n" \
        "Upgrade: WebSocket\r\n" \
        "Connection: Upgrade\r\n" \
        "Sec-WebSocket-Key: " + base64.b64encode('too long. too long. too long') + "\r\n" \
        "Sec-WebSocket-Origin: http://localhost\r\n" \
        "Sec-WebSocket-Protocol: chat, superchat\r\n" \
        "Sec-WebSocket-Version: 7\r\n" \
        "\r\n"

        fd.write(headers)
        try:
            response = read_http(fd)
        except ConnectionClosed:
            closed = True

        assert closed, "Failed to abort connection with key that is too long"
        fd.close()

    def test_good_handshake(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        response = read_http(fd, code=101, reason="Switching Protocols")
        response.assertHeader("Upgrade", "websocket")
        response.assertHeader("Connection", "Upgrade")
        response.assertHeader("Sec-WebSocket-Accept", "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

        fd.close();

    def test_send_short_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason="Switching Protocols")

        msg = 'Hello, websocket'
        self.ws.send(1, msg)

        preamble = fd.read(2)
        opcode, length = struct.unpack('!BB', preamble)

        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 1, 'Opcode must be 0x1'
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == len(msg), 'Wrong length %d, expected %d' % (length, len(msg))

        rxd_msg = fd.read(length).decode('utf-8', 'replace')
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close()

    def test_send_medium_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason="Switching Protocols")

        msg = 'Hello, websocket' * 8
        self.ws.send(1, msg)

        preamble = fd.read(4)
        opcode, length_code, length = struct.unpack('!BBH', preamble)

        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 1, 'Opcode must be 0x1'
        assert (length_code & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length_code == 126, 'The length code must be 126'
        assert length == len(msg), 'Wrong length %d, expected %d' % (length, len(msg))

        rxd_msg = fd.read(length).decode('utf-8', 'replace')
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close()

    def test_send_long_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason="Switching Protocols")

        msg = 'Hello, websocket' * 4098
        self.ws.send(1, msg)

        preamble = fd.read(10)
        opcode, length_code, length = struct.unpack('!BBQ', preamble)

        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 1, 'Opcode must be 0x1'
        assert (length_code & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length_code == 127, 'The length code must be 127'
        assert length == len(msg), 'Wrong length %d, expected %d' % (length, len(msg))

        rxd_msg = fd.read(length).decode('utf-8', 'replace')
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close()

    def test_binary_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason="Switching Protocols")

        msg = struct.pack('!BHB', 129, 23, 42)
        self.ws.send(2, msg)

        frame = fd.read(6)
        opcode, length, first, second, third = struct.unpack('!BBBHB', frame)

        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 2, 'Opcode must be 0x2'
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == 4, 'Wrong length %d, expected 4' % length
        assert first == 129, 'Expected first value to be 129, but got %d' % first
        assert second == 23, 'Expected second value to be 23, but got %d' % second
        assert third == 42, 'Expected third value to be 42, but got %d' % third

        fd.close()

    def test_wait_bad_framing_reserved_bits(self):
        for reserved_bits in xrange(1, 8):
            fd = self.connect().makefile(bufsize=1)

            fd.write(self.GOOD_HEADERS)
            read_http(fd, code=101, reason='Switching Protocols')

            expected_msg = 'Reserved bits cannot be set'

            bad_opcode = WebSocketVersion7.FIN | (reserved_bits << 4) | WebSocketVersion7.OPCODE_TEXT
            fd.write(struct.pack('!BB', bad_opcode, int('10000000', 2)))

            frame = self.ws.wait()
            assert self.ws.websocket_closed, \
                    'Failed to close connection when sent a frame with reserved bits set'

            preamble = fd.read(2)

            opcode, length = struct.unpack('!BB', preamble)
            assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
            assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
            assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

            reason = fd.read(2)
            reason = struct.unpack('!H', reason)[0]
            assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

            rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

            fd.close();

    def test_wait_bad_opcode(self):
        bad_opcodes = range(WebSocketVersion7.OPCODE_BINARY + 1, WebSocketVersion7.OPCODE_CLOSE)
        bad_opcodes += range(WebSocketVersion7.OPCODE_PONG + 1, 2**4)
        for bad_opcode in bad_opcodes:
            fd = self.connect().makefile(bufsize=1)

            fd.write(self.GOOD_HEADERS)
            read_http(fd, code=101, reason='Switching Protocols')

            expected_msg = 'Invalid opcode %x' % bad_opcode

            bad_opcode = WebSocketVersion7.FIN | bad_opcode
            fd.write(struct.pack('!BB', bad_opcode, int('10000000', 2)))

            frame = self.ws.wait()
            assert self.ws.websocket_closed, \
                    'Failed to close connection when sent a frame with unsupported opcode'

            preamble = fd.read(2)

            opcode, length = struct.unpack('!BB', preamble)
            assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
            assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
            assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

            reason = fd.read(2)
            reason = struct.unpack('!H', reason)[0]
            assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

            rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

            fd.close();

    def test_wait_no_mask(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = 'MASK must be set'

        fd.write(struct.pack('!BB',
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_TEXT, int('00000000', 2)))

        frame = self.ws.wait()
        assert self.ws.websocket_closed, \
                'Failed to close connection when sent a frame with MASK not set'

        preamble = fd.read(2)

        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

        reason = fd.read(2)
        reason = struct.unpack('!H', reason)[0]
        assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

        rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
        assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def _get_payload(self, mask, msg):
        mask_octets = struct.unpack('!BBBB', struct.pack('!L', mask))
        msg = unicode(msg).encode('utf-8')
        result = ''
        j = 0
        for c in msg:
            result += chr(ord(c) ^ mask_octets[j])
            j = (j + 1) % 4
        return result

    def test_wait_short_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket'
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_med_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket' * 8
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBHL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | 126, length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_long_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket' * 8 #4098
        mask = 42
        encoded_msg = self._get_payload(42, msg)
        length = len(encoded_msg)
        payload = struct.pack('!BBQL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | 127, length, mask, encoded_msg)
        fd.write(payload)

        self.ws._waiter = 'test'
        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_control_frames_of_unusual_size(self):
        opcodes = [WebSocketVersion7.OPCODE_CLOSE,
                WebSocketVersion7.OPCODE_PING,
                WebSocketVersion7.OPCODE_PONG]
        expected_msg = 'Control frame payload cannot be larger than 125 bytes'
        for test_opcode in opcodes:
            msg = ''
            mask = 0x42424242
            encoded_msg = self._get_payload(mask, msg)

            fd = self.connect().makefile(bufsize=1)

            fd.write(self.GOOD_HEADERS)
            read_http(fd, code=101, reason='Switching Protocols')

            fd.write(struct.pack('!BBHL',
                WebSocketVersion7.FIN | test_opcode, 
                WebSocketVersion7.MASK | 126, 0, mask))

            frame = self.ws.wait()
            assert self.ws.websocket_closed, \
                    'Failed to close connection when sent a frame of unusual size'

            preamble = fd.read(2)

            opcode, length = struct.unpack('!BB', preamble)
            assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
            assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
            assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

            reason = fd.read(2)
            reason = struct.unpack('!H', reason)[0]
            assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

            rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

            fd.close();

            fd = self.connect().makefile(bufsize=1)

            fd.write(self.GOOD_HEADERS)
            read_http(fd, code=101, reason='Switching Protocols')

            fd.write(struct.pack('!BBQL',
                WebSocketVersion7.FIN | test_opcode, 
                WebSocketVersion7.MASK | 127, length, mask))

            frame = self.ws.wait()
            assert self.ws.websocket_closed, \
                    'Failed to close connection when sent a frame of unusual size'

            preamble = fd.read(2)

            opcode, length = struct.unpack('!BB', preamble)
            assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
            assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
            assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

            reason = fd.read(2)
            reason = struct.unpack('!H', reason)[0]
            assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

            rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

            fd.close();

    def test_wait_close_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket'
        mask = 0x42424242
        reason = 1000
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg) + 2
        fd.write(struct.pack('!BBLH%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_CLOSE,
            WebSocketVersion7.MASK | length, mask, reason ^ (mask >> 16), encoded_msg))

        rxd_msg = self.ws.wait()
        assert self.ws.websocket_closed, 'Did not close connection when sent a close frame'
        assert rxd_msg == (reason, msg), 'Wrong result "%s"' % (rxd_msg,)

        preamble = fd.read(2)
        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == WebSocketVersion7.OPCODE_CLOSE, \
                'Opcode must be %x' % WebSocketVersion7.OPCODE_CLOSE
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == 2, 'The payload length must be 2, but got %d' % length
        
        reason = struct.unpack('!H', fd.read(2))[0]
        assert reason == 1000, 'The reason must be 1000, but got %d' % reason

        fd.close();

    def test_wait_close_frame_no_payload(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = ''
        mask = 0x42424242
        encoded_msg = self._get_payload(mask, msg)
        length = 0
        fd.write(struct.pack('!BBL',
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_CLOSE,
            WebSocketVersion7.MASK | length, mask))

        rxd_msg = self.ws.wait()
        assert self.ws.websocket_closed, \
                'Did not close connection when sent a close frame with no payload'
        assert rxd_msg == (None, None), 'Wrong result "%s"' % (rxd_msg,)

        preamble = fd.read(2)
        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == WebSocketVersion7.OPCODE_CLOSE, \
                'Opcode must be %x' % WebSocketVersion7.OPCODE_CLOSE
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == 2, 'The payload length must be 2, but got %d' % length
        
        reason = struct.unpack('!H', fd.read(2))[0]
        assert reason == WebSocketVersion7.REASON_NORMAL, \
                'The reason must be 1000, but got %d' % reason

        fd.close();

    def test_wait_ping_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket'
        mask = 0x42424242
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_PING,
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a ping frame'
        assert rxd_msg == (WebSocketVersion7.OPCODE_PING, msg.encode('utf-8')), \
                'Wrong result "%s"' % (rxd_msg,)

        preamble = fd.read(2)
        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == WebSocketVersion7.OPCODE_PONG, \
                'Opcode must be %x' % WebSocketVersion7.OPCODE_PONG
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == len(encoded_msg), 'Wrong payload length. Got %d' % length

        txd_msg = fd.read(length)
        assert txd_msg == msg.encode('utf-8'), 'Wrong message "%s", expected "%s"' % (txd_msg, msg)

        fd.close();

    def test_wait_pong_frame(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        msg = 'Hello, websocket'
        mask = 0x42424242
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_PONG,
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a pong frame'
        assert rxd_msg == (WebSocketVersion7.OPCODE_PONG, msg.encode('utf-8')), \
                'Wrong result "%s"' % (rxd_msg,)

        fd.close();

    def test_wait_fragmented_control_frame(self):
        opcodes = [WebSocketVersion7.OPCODE_CLOSE,
                WebSocketVersion7.OPCODE_PING,
                WebSocketVersion7.OPCODE_PONG]
        expected_msg = 'Control frames cannot be fragmented'
        for test_opcode in opcodes:
            msg = ''
            mask = 0x42424242
            encoded_msg = self._get_payload(mask, msg)

            fd = self.connect().makefile(bufsize=1)

            fd.write(self.GOOD_HEADERS)
            read_http(fd, code=101, reason='Switching Protocols')

            fd.write(struct.pack('!BBL', test_opcode, WebSocketVersion7.MASK | 0, mask))

            frame = self.ws.wait()
            assert self.ws.websocket_closed, \
                    'Failed to close connection when sent a fragmented control frame'

            preamble = fd.read(2)

            opcode, length = struct.unpack('!BB', preamble)
            assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
            assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
            assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

            reason = fd.read(2)
            reason = struct.unpack('!H', reason)[0]
            assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

            rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

            fd.close();

    def test_wait_unfinished_fragmented_message(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = 'Received new unfragmented data frame during fragmented message'

        msg = 'Hello, '
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        frame = self.ws.wait()
        assert self.ws.websocket_closed, \
                'Failed to close connection when sent new unfragmented ' + \
                'data frame during fragmented message'

        preamble = fd.read(2)

        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

        reason = fd.read(2)
        reason = struct.unpack('!H', reason)[0]
        assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

        rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
        assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_bad_fragment_opcode(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = 'Received new fragment frame with non-zero opcode'

        msg = 'Hello, '
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        frame = self.ws.wait()
        assert self.ws.websocket_closed, \
                'Failed to close connection when sent fragment with non-zero opcode'

        preamble = fd.read(2)

        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == 8, 'Opcode must be 0x8'
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'

        reason = fd.read(2)
        reason = struct.unpack('!H', reason)[0]
        assert reason == 1002, 'Expected reason to be 1002, but got %d' % reason

        rxd_msg = fd.read(length - 2).decode('utf-8', 'replace')
        assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_two_fragments(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = ''

        msg = 'Hello, '
        expected_msg += msg
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        msg = 'websocket'
        expected_msg += msg
        mask = 23
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_FRAG, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_three_fragments(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = ''

        msg = 'Hello, '
        expected_msg += msg
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        msg = 'websocket'
        expected_msg += msg
        mask = 1337
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_FRAG, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        msg = '!'
        expected_msg += msg
        mask = 23
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_FRAG, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();

    def test_wait_control_frame_during_fragmented_message(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        expected_msg = ''

        msg = 'Hello, '
        expected_msg += msg
        mask = 42
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.OPCODE_TEXT, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        ping_msg = 'Marco!'
        mask = 0x42424242
        encoded_ping_msg = self._get_payload(mask, ping_msg)
        length = len(encoded_ping_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_PING,
            WebSocketVersion7.MASK | length, mask, encoded_ping_msg))

        msg = 'websocket'
        expected_msg += msg
        mask = 23
        encoded_msg = self._get_payload(mask, msg)
        length = len(encoded_msg)
        fd.write(struct.pack('!BBL%ds' % length,
            WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_FRAG, 
            WebSocketVersion7.MASK | length, mask, encoded_msg))

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a ping frame'
        assert rxd_msg == (WebSocketVersion7.OPCODE_PING, ping_msg.encode('utf-8')), \
                'Wrong result "%s"' % (rxd_msg,)

        preamble = fd.read(2)
        opcode, length = struct.unpack('!BB', preamble)
        assert opcode & WebSocketVersion7.FIN, 'FIN must be set'
        assert (opcode & WebSocketVersion7.OPCODE) == WebSocketVersion7.OPCODE_PONG, \
                'Opcode must be %x' % WebSocketVersion7.OPCODE_PONG
        assert (length & WebSocketVersion7.MASK) == 0, 'MASK must not be set'
        assert length == len(encoded_ping_msg), 'Wrong payload length. Got %d' % length

        txd_msg = fd.read(length)
        assert txd_msg == ping_msg.encode('utf-8'), \
                'Wrong message "%s", expected "%s"' % (txd_msg, ping_msg)

        rxd_msg = self.ws.wait()
        assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
        assert rxd_msg == expected_msg, \
                'Wrong message "%s", expected "%s"' % (rxd_msg, expected_msg)

        fd.close();

    def test_wait_two_fragmented_messages(self):
        fd = self.connect().makefile(bufsize=1)

        fd.write(self.GOOD_HEADERS)
        read_http(fd, code=101, reason='Switching Protocols')

        for x in xrange(0, 2):
            expected_msg = ''

            msg = 'Hello, '
            expected_msg += msg
            mask = 42
            encoded_msg = self._get_payload(mask, msg)
            length = len(encoded_msg)
            fd.write(struct.pack('!BBL%ds' % length,
                WebSocketVersion7.OPCODE_TEXT, 
                WebSocketVersion7.MASK | length, mask, encoded_msg))

            msg = 'websocket %d' % x
            expected_msg += msg
            mask = 23
            encoded_msg = self._get_payload(mask, msg)
            length = len(encoded_msg)
            fd.write(struct.pack('!BBL%ds' % length,
                WebSocketVersion7.FIN | WebSocketVersion7.OPCODE_FRAG, 
                WebSocketVersion7.MASK | length, mask, encoded_msg))

            rxd_msg = self.ws.wait()
            assert not self.ws.websocket_closed, 'Closed connection when sent a good frame'
            assert rxd_msg == expected_msg, 'Wrong message "%s"' % rxd_msg

        fd.close();
    """
    TODO: write fragmentation test cases:
          - too large of a message
            - make this a config attribute that applies to individual messages as well
    """

if __name__ == '__main__':
    greentest.main()
