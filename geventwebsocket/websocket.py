from socket import error as socket_error
import struct
from gevent.coros import Semaphore


class Closed(object):

    def __init__(self, reason, message):
        self.reason = reason
        self.message = message

    def __nonzero__(self):
        return False

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self.reason, self.message)


class WebSocketError(socket_error):
    pass


class FrameTooLargeException(WebSocketError):
    pass


class WebSocket(object):

    def _encode_text(self, s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        elif isinstance(s, str):
            return s
        else:
            raise TypeError("Expected 'unicode' or utf-8-encoded string: %r" % (s, ))


class WebSocketHixie(WebSocket):

    def __init__(self, fobj, environ):
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL')
        self.path = environ.get('PATH_INFO')
        self._writelock = Semaphore(1)
        self.fobj = fobj
        self._write = _get_write(fobj)

    def send(self, message):
        message = self._encode_text(message)

        with self._writelock:
            self._write("\x00" + message + "\xFF")

    def close(self):
        if self.fobj is not None:
            self.fobj.close()
            self.fobj = None

    def _message_length(self):
        length = 0

        while True:
            if self.fobj is None:
                raise WebSocketError('Connenction closed unexpectedly while reading message length')
            byte_str = self.fobj.read(1)

            if not byte_str:
                return 0
            else:
                byte = ord(byte_str)

            if byte != 0x00:
                length = length * 128 + (byte & 0x7f)
                if (byte & 0x80) != 0x80:
                    break

        return length

    def _read_until(self):
        bytes = []

        read = self.fobj.read

        while True:
            if self.fobj is None:
                msg = ''.join(bytes)
                raise WebSocketError('Connection closed unexpectedly while reading message: %r' % msg)
            byte = read(1)
            if ord(byte) != 0xff:
                bytes.append(byte)
            else:
                break

        return ''.join(bytes)

    def receive(self):
        read = self.fobj.read
        while self.fobj is not None:
            frame_str = read(1)
            if not frame_str:
                self.close()
                return
            else:
                frame_type = ord(frame_str)

            if frame_type == 0x00:
                bytes = self._read_until()
                return bytes.decode("utf-8", "replace")
            else:
                raise WebSocketError("Received an invalid frame_type=%r" % frame_type)


class WebSocketHybi(WebSocket):
    FIN = int("10000000", 2)
    RSV = int("01110000", 2)
    OPCODE = int("00001111", 2)
    MASK = int("10000000", 2)
    PAYLOAD = int("01111111", 2)

    OPCODE_CONTINUATION = 0x0
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    REASON_NORMAL = 1000
    REASON_GOING_AWAY = 1001
    REASON_PROTOCOL_ERROR = 1002
    REASON_UNSUPPORTED_DATA_TYPE = 1003
    REASON_TOO_LARGE = 1004

    LEN_16 = 126
    LEN_64 = 127

    def __init__(self, fobj, environ):
        self.origin = environ.get('HTTP_SEC_WEBSOCKET_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self._chunks = bytearray()
        self._first_opcode = None
        self._writelock = Semaphore(1)
        self.fobj = fobj
        self._write = _get_write(fobj)

    def _parse_header(self, data):
        if len(data) != 2:
            self.close()
            raise WebSocketError('Incomplete read while reading header: %r' % data)
        first_byte, second_byte = struct.unpack('!BB', data)

        fin = (first_byte >> 7) & 1
        rsv1 = (first_byte >> 6) & 1
        rsv2 = (first_byte >> 5) & 1
        rsv3 = (first_byte >> 4) & 1
        opcode = first_byte & 0xf

        # frame-fin = %x0 ; more frames of this message follow
        #           / %x1 ; final frame of this message

        # frame-rsv1 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        # frame-rsv2 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        # frame-rsv3 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
        if rsv1 or rsv2 or rsv3:
            self.close()
            raise WebSocketError('Reserved bits cannot be set: %r' % data)

        #if self._is_invalid_opcode(opcode):
        #    raise WebSocketError('Invalid opcode %x' % opcode)

        # control frames cannot be fragmented
        if opcode > 0x7 and fin == 0:
            self.close()
            raise WebSocketError('Control frames cannot be fragmented: %r' % data)

        if len(self._chunks) > 0 and fin == 0 and opcode != self.OPCODE_CONTINUATION:
            self.close(self.REASON_PROTOCOL_ERROR, 'Received new fragment frame with non-zero opcode')
            raise WebSocketError('Received new fragment frame with non-zero opcode: %r' % data)

        if len(self._chunks) > 0 and fin == 1 and (self.OPCODE_TEXT <= opcode <= self.OPCODE_BINARY):
            self.close(self.REASON_PROTOCOL_ERROR, 'Received new unfragmented data frame during fragmented message')
            raise WebSocketError('Received new unfragmented data frame during fragmented message: %r' % data)

        mask = (second_byte >> 7) & 1
        length = (second_byte) & 0x7f

        #if not self.MASK & length_octet: # TODO: where is this in the docs?
        #    self.close(self.REASON_PROTOCOL_ERROR, 'MASK must be set')

        # Control frames MUST have a payload length of 125 bytes or less
        if opcode > 0x7 and length > 125:
            self.close()
            raise FrameTooLargeException("Control frame payload cannot be larger than 125 bytes: %r" % data)

        return fin, opcode, mask, length

    def receive(self):
        """Return the next frame from the socket."""
        if self.fobj is None:
            return

        read = self.fobj.read

        while True:
            data0 = read(2)
            if not data0:
                self._close()
                return

            fin, opcode, mask, length = self._parse_header(data0)

            if length < 126:
                data1 = ''
            elif length == 126:
                data1 = read(2)
                if len(data1) != 2:
                    self.close()
                    raise WebSocketError('Incomplete read while reading 2-byte length: %r' % (data0 + data1))
                length = struct.unpack('!H', data1)[0]
            elif length == 127:
                data1 = read(8)
                if len(data1) != 8:
                    self.close()
                    raise WebSocketError('Incomplete read while reading 8-byte length: %r' % (data0 + data1))
                length = struct.unpack('!Q', data1)[0]
            else:
                self.close()
                raise WebSocketError('Invalid length: %r' % data0)

            # Unmask the payload if necessary
            if mask and length:
                data2 = read(4)
                if len(data2) != 4:
                    self.close()
                    raise WebSocketError('Incomplete read while reading mask: %r' % (data0 + data1 + data2))
                masking_key = struct.unpack('!BBBB', data2)
            else:
                data2 = ''

            if length:
                payload = read(length)
                if len(payload) != length:
                    self.close()
                    args = (length, data0 + data1 + data2, payload)
                    raise WebSocketError('Incomplete read (expected message of %s bytes): %r %r' % args)
            else:
                payload = ''

            if mask:
                # XXX message from client actually should always be masked
                masked_payload = bytearray(payload)

                for i in range(len(masked_payload)):
                    masked_payload[i] = masked_payload[i] ^ masking_key[i%4]

                payload = masked_payload

            if opcode == self.OPCODE_TEXT:
                self._first_opcode = opcode
                if payload:
                    # XXX given that we have OPCODE_CONTINUATION, shouldn't we just reset _chunks here?
                    self._chunks.extend(payload)
            elif opcode == self.OPCODE_BINARY:
                self._first_opcode = opcode
                if payload:
                    self._chunks.extend(payload)
            elif opcode == self.OPCODE_CONTINUATION:
                self._chunks.extend(payload)
            elif opcode == self.OPCODE_CLOSE:
                if length >= 2:
                    reason, message = struct.unpack('!H%ds' % (length - 2), buffer(payload))
                else:
                    reason = message = None
                self.close(self.REASON_NORMAL, '')
                return Closed(reason, message)
            elif opcode == self.OPCODE_PING:
                self.send(payload, opcode=self.OPCODE_PONG)
                continue
            elif opcode == self.OPCODE_PONG:
                continue
            else:
                self.close()
                raise WebSocketError("Unexpected opcode=%r" % (opcode, ))

            if fin == 1:
                if self._first_opcode == self.OPCODE_TEXT:
                    msg = self._chunks.decode("utf-8")
                else:
                    msg = self._chunks

                self._first_opcode = False
                self._chunks = bytearray()

                return msg

    def _is_valid_opcode(self, opcode):
        return opcode in (self.OPCODE_CONTINUATION, self.OPCODE_TEXT, self.OPCODE_BINARY,
            self.OPCODE_CLOSE, self.OPCODE_PING, self.OPCODE_PONG)

    def send(self, message, opcode=OPCODE_TEXT):
        """Send a frame over the websocket with message as its payload

        Keyword args:
        opcode -- the opcode to use (default OPCODE_TEXT)
        """

        if not self._is_valid_opcode(opcode):
            raise ValueError('Invalid opcode %d' % opcode)

        if opcode == self.OPCODE_TEXT:
            message = self._encode_text(message)

        # TODO: implement fragmented messages
        mask_bit = 0
        fin = 1

        ## +-+-+-+-+-------+
        ## |F|R|R|R| opcode|
        ## |I|S|S|S|  (4)  |
        ## |N|V|V|V|       |
        ## | |1|2|3|       |
        ## +-+-+-+-+-------+
        header = chr(
            (fin << 7) |
            (0 << 6) | # RSV1
            (0 << 5) | # RSV2
            (0 << 4) | # RSV3
            opcode
        )

        ##                 +-+-------------+-------------------------------+
        ##                 |M| Payload len |    Extended payload length    |
        ##                 |A|     (7)     |             (16/63)           |
        ##                 |S|             |   (if payload len==126/127)   |
        ##                 |K|             |                               |
        ## +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
        ## |     Extended payload length continued, if payload len == 127  |
        ## + - - - - - - - - - - - - - - - +-------------------------------+

        msg_length = len(message)

        if opcode == self.OPCODE_TEXT:
            message = struct.pack('!%ds' % msg_length, message)

        if msg_length < 126:
            header += chr(mask_bit | msg_length)
        elif msg_length < (1 << 16):
            header += chr(mask_bit | 126) + struct.pack('!H', msg_length)
        elif msg_length < (1 << 63):
            header += chr(mask_bit | 127) + struct.pack('!Q', msg_length)
        else:
            raise FrameTooLargeException()

        with self._writelock:
            self._write(header + message)

    def close(self, reason=1000, message=''):
        """Close the websocket, sending the specified reason and message"""
        if self.fobj is not None:
            message = self._encode_text(message)
            self.send(struct.pack('!H%ds' % len(message), reason, message), opcode=self.OPCODE_CLOSE)
            self.fobj.close()
            self.fobj = None

    def _close(self):
        if self.fobj is not None:
            self.fobj.close()
            self.fobj = None


class write_method(object):

    def __init__(self, fobj):
        self.fobj = fobj

    def __call__(self, data):
        return self.fobj.write(data)


def _get_write(fobj):
    flush = getattr(fobj, 'flush', None)
    if flush is not None:
        flush()
    sock = getattr(fobj, '_sock', None)
    if sock is not None:
        sendall = getattr(sock, 'sendall', None)
        if sendall is not None:
            return sendall
    write = getattr(fobj, 'write', None)
    if write is not None:
        return write
    return write_method(fobj)


# XXX avoid small recv()s ?
