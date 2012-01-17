from socket import error as socket_error
import struct
from gevent.coros import Semaphore


class WebSocketError(socket_error):
    pass


class FrameTooLargeException(WebSocketError):
    pass


class WebSocket(object):

    def _encode_text(self, s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        else:
            return s


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
            self._write = None

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
    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    def __init__(self, fobj, environ):
        self.origin = environ.get('HTTP_SEC_WEBSOCKET_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self._chunks = bytearray()
        self._writelock = Semaphore(1)
        self.fobj = fobj
        self._write = _get_write(fobj)
        self.close_code = None
        self.close_message = None

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
            self.close(1002)
            raise WebSocketError('Received frame with non-zero reserved bits: %r' % data)

        if opcode > 0x7 and fin == 0:
            self.close(1002)
            raise WebSocketError('Received fragmented control frame: %r' % data)

        if len(self._chunks) > 0 and fin == 0 and not opcode:
            self.close(1002)
            raise WebSocketError('Received new fragment frame with non-zero opcode: %r' % data)

        if len(self._chunks) > 0 and fin == 1 and (self.OPCODE_TEXT <= opcode <= self.OPCODE_BINARY):
            self.close(1002)
            raise WebSocketError('Received new unfragmented data frame during fragmented message: %r' % data)

        has_mask = (second_byte >> 7) & 1
        length = (second_byte) & 0x7f

        # Control frames MUST have a payload length of 125 bytes or less
        if opcode > 0x7 and length > 125:
            self.close(1002)
            raise FrameTooLargeException("Control frame payload cannot be larger than 125 bytes: %r" % data)

        return fin, opcode, has_mask, length

    def receive_frame(self):
        """Return the next frame from the socket."""
        if self.fobj is None:
            return

        read = self.fobj.read

        data0 = read(2)
        if not data0:
            self._close()
            return

        fin, opcode, has_mask, length = self._parse_header(data0)

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

        if has_mask:
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
                args = (length, len(payload))
                raise WebSocketError('Incomplete read: expected message of %s bytes, got %s bytes' % args)
        else:
            payload = ''

        if has_mask and payload:
            # XXX message from client actually should always be masked
            masked_payload = bytearray(payload)

            for i in range(len(masked_payload)):
                masked_payload[i] = masked_payload[i] ^ masking_key[i % 4]

            payload = masked_payload

        return fin, opcode, payload

    def _receive(self):
        """Return the next text or binary message from the socket."""
        opcode = None
        result = bytearray()
        while True:
            frame = self.receive_frame()
            if frame is None:
                if result:
                    raise WebSocketError('Peer closed connection unexpectedly')
                return

            f_fin, f_opcode, f_payload = frame

            if f_opcode in (self.OPCODE_TEXT, self.OPCODE_BINARY):
                if opcode is None:
                    opcode = f_opcode
                else:
                    raise WebSocketError('The opcode in non-fin frame is expected to be zero, got %r' % (f_opcode, ))
            elif not f_opcode:
                if opcode is None:
                    self.close(1002)
                    raise WebSocketError('Unexpected frame with opcode=0')
            elif f_opcode == self.OPCODE_CLOSE:
                if len(f_payload) >= 2:
                    self.close_code = struct.unpack('!H', str(f_payload[:2]))[0]
                    self.close_message = f_payload[2:]
                elif f_payload:
                    self._close()
                    raise WebSocketError('Invalid close frame: %s %s %s' % (f_fin, f_opcode, repr(f_payload)))
                code = self.close_code
                if code is None or (code >= 1000 and code < 5000):
                    self.close()
                else:
                    self.close(1002)
                    raise WebSocketError('Received invalid close frame: %r %r' % (code, self.close_message))
                return
            elif f_opcode == self.OPCODE_PING:
                self.send_frame(f_payload, opcode=self.OPCODE_PONG)
                continue
            elif f_opcode == self.OPCODE_PONG:
                continue
            else:
                self._close()  # XXX should send proper reason?
                raise WebSocketError("Unexpected opcode=%r" % (f_opcode, ))

            result.extend(f_payload)
            if f_fin:
                break

        if opcode == self.OPCODE_TEXT:
            return result, False
        elif opcode == self.OPCODE_BINARY:
            return result, True
        else:
            raise AssertionError('internal serror in gevent-websocket: opcode=%r' % (opcode, ))

    def receive(self):
        result = self._receive()
        if not result:
            return result
        message, is_binary = result
        if is_binary:
            return message
        else:
            try:
                return message.decode('utf-8')
            except ValueError:
                self.close(1007)
                raise

    def send_frame(self, message, opcode):
        """Send a frame over the websocket with message as its payload"""
        header = chr(0x80 | opcode)

        if isinstance(message, unicode):
            message = message.encode('utf-8')

        msg_length = len(message)

        if msg_length < 126:
            header += chr(msg_length)
        elif msg_length < (1 << 16):
            header += chr(126) + struct.pack('!H', msg_length)
        elif msg_length < (1 << 63):
            header += chr(127) + struct.pack('!Q', msg_length)
        else:
            raise FrameTooLargeException()

        try:
            combined = header + message
        except TypeError:
            with self._writelock:
                self._write(header)
                self._write(message)
        else:
            with self._writelock:
                self._write(combined)

    def send(self, message, binary=None):
        """Send a frame over the websocket with message as its payload"""
        if binary is None:
            binary = not isinstance(message, (str, unicode))

        if binary:
            return self.send_frame(message, self.OPCODE_BINARY)
        else:
            return self.send_frame(message, self.OPCODE_TEXT)

    def close(self, code=1000, message=''):
        """Close the websocket, sending the specified code and message"""
        if self.fobj is not None:
            message = self._encode_text(message)
            self.send_frame(struct.pack('!H%ds' % len(message), code, message), opcode=self.OPCODE_CLOSE)
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
