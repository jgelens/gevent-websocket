import struct

class WebSocket(object):
    pass


class ProtocolException(Exception):
    pass


class FrameTooLargeException(Exception):
    pass


class WebSocketLegacy(object):
    def __init__(self, sock, rfile, environ):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL')
        self.path = environ.get('PATH_INFO')
        self.websocket_closed = False

    def send(self, message):
        if self.websocket_closed:
            raise Exception("Connection was terminated")

        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif isinstance(message, str):
            message = unicode(message, 'utf-8').encode('utf-8')
        else:
            raise Exception("Invalid message encoding")

        self.socket.sendall("\x00" + message + "\xFF")

    def close_connection(self):
        if not self.websocket_closed:
            self.websocket_closed = True
            self.socket.shutdown(True)
            self.socket.close()
        else:
            return

    def _message_length(self):
        length = 0

        while True:
            byte_str = self.rfile.read(1)

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

        while True:
            byte = self.rfile.read(1)
            if ord(byte) != 0xff:
                bytes.append(byte)
            else:
                break

        return ''.join(bytes)

    def receive(self):
        while True:
            if self.websocket_closed:
                return None

            frame_str = self.rfile.read(1)
            if not frame_str:
                # Connection lost?
                self.websocket_closed = True
                continue
            else:
                frame_type = ord(frame_str)


            if (frame_type & 0x80) == 0x00: # most significant byte is not set

                if frame_type == 0x00:
                    bytes = self._read_until()
                    return bytes.decode("utf-8", "replace")
                else:
                    self.websocket_closed = True

            elif (frame_type & 0x80) == 0x80: # most significant byte is set
                # Read binary data (forward-compatibility)
                if frame_type != 0xff:
                    self.websocket_closed = True
                else:
                    length = self._message_length()
                    if length == 0:
                        self.websocket_closed = True
                    else:
                        self.rfile.read(length) # discard the bytes
            else:
                raise IOError("Reveiced an invalid message")


class WebSocketVersion7(WebSocketLegacy):
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

    def __init__(self, sock, rfile, environ, compatibility_mode=True):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_SEC_WEBSOCKET_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self.websocket_closed = False
        self._chunks = bytearray()
        self._first_opcode = None

    def _read_from_socket(self, count):
        return self.rfile.read(count)

    def receive(self):
        """Return the next frame from the socket

        If the next frame is invalid, wait closes the socket and returns None.

        If the next frame is valid and the websocket instance's
        compatibility_mode attribute is True, then wait ignores PING and PONG
        frames, returns None when sent a CLOSE frame and returns the payload
        for data frames.

        If the next frame is valid and the websocket instance's
        compatibility_mode attribute is False, it returns a tuple of the form
        (opcode, payload).
        """

        while True:
            if self.websocket_closed:
                return None

            payload = ""
            first_byte, second_byte = struct.unpack('!BB', self._read_from_socket(2))

            fin = (first_byte >> 7) & 1
            rsv1 = (first_byte >> 6) & 1
            rsv2 = (first_byte >> 5) & 1
            rsv3 = (first_byte >> 4) & 1
            opcode = first_byte & 0xf

            # frame-fin = %x0 ; more frames of this message follow
            #           / %x1 ; final frame of this message
            if fin not in (0, 1):
                raise ProtocolException("")

            # frame-rsv1 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
            # frame-rsv2 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
            # frame-rsv3 = %x0 ; 1 bit, MUST be 0 unless negotiated otherwise
            if rsv1 or rsv2 or rsv3:
                raise ProtocolException('Reserved bits cannot be set')

            #if self._is_invalid_opcode(opcode):
            #    raise ProtocolException('Invalid opcode %x' % opcode)

            # control frames cannot be fragmented
            if opcode > 0x7 and fin == 0:
                raise ProtocolException('Control frames cannot be fragmented')

            if len(self._chunks) > 0 and \
                    fin == 0 and opcode != self.OPCODE_CONTINUATION:
                self.close(self.REASON_PROTOCOL_ERROR,
                        'Received new fragment frame with non-zero opcode')
                return

            if len(self._chunks) > 0 and \
                    fin == 1 and (self.OPCODE_TEXT <= opcode <= self.OPCODE_BINARY):
                self.close(self.REASON_PROTOCOL_ERROR,
                        'Received new unfragmented data frame during fragmented message')

            mask = (second_byte >> 7) & 1
            payload_length = (second_byte) & 0x7f

            #if not self.MASK & length_octet: # TODO: where is this in the docs?
            #    self.close(self.REASON_PROTOCOL_ERROR, 'MASK must be set')

            # Control frames MUST have a payload length of 125 bytes or less
            if opcode > 0x7 and payload_length > 125:
                raise FrameTooLargeException("Control frame payload cannot be larger than 125 bytes")

            if payload_length < 126:
                length = payload_length
            elif payload_length == 126:
                length = struct.unpack('!H', self._read_from_socket(2))[0]
            elif payload_length == 127:
                length = struct.unpack('!Q', self._read_from_socket(8))[0]
            else:
                raise ProtocolException('Calculated invalid length')

            payload = ""

            # Unmask the payload if necessary
            if mask:
                masking_key = struct.unpack('!BBBB', self._read_from_socket(4))
                masked_payload = self._read_from_socket(length)

                masked_payload = bytearray(masked_payload)

                for i in range(len(masked_payload)):
                    masked_payload[i] = masked_payload[i] ^ masking_key[i%4]

                payload = masked_payload

            # Read application data
            if opcode == self.OPCODE_TEXT:
                self._first_opcode = opcode
                self._chunks.extend(payload)

            elif opcode == self.OPCODE_BINARY:
                self._first_opcode = opcode
                self._chunks.extend(payload)

            elif opcode == self.OPCODE_CONTINUATION:
                if len(self._chunks) != 0:
                    raise ProtocolException("Cannot continue a non started message")

                self._chunks.extend(payload)

            elif opcode == self.OPCODE_CLOSE:
                if length >= 2:
                    reason, message = struct.unpack('!H%ds' % (length - 2), payload)
                else:
                    reason = message = None

                self.close(self.REASON_NORMAL, '')
                if not self.compatibility_mode:
                    return (self.OPCODE_CLOSE, (reason, message))
                else:
                    return None

            elif opcode == self.OPCODE_PING:
                self.send(payload, opcode=self.OPCODE_PONG)

                if not self.compatibility_mode:
                    return (self.OPCODE_PING, payload)
                else:
                    continue

            elif opcode == self.OPCODE_PONG:
                if not self.compatibility_mode:
                    return (self.OPCODE_PONG, payload)
                else:
                    continue
            else:
                raise Exception("Shouldn't happen")

            if fin == 1:
                if self._first_opcode == self.OPCODE_TEXT:
                    msg = self._chunks.decode("utf-8")
                else:
                    msg = self._chunks

                self._first_opcode = False
                self._chunks = bytearray()

                return msg


    def _encode_text(self, s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        elif isinstance(s, str):
            return unicode(s).encode('utf-8')
        else:
            raise Exception('Invalid encoding')

    def _is_valid_opcode(self, opcode):
        return opcode in (self.OPCODE_CONTINUATION, self.OPCODE_TEXT, self.OPCODE_BINARY,
            self.OPCODE_CLOSE, self.OPCODE_PING, self.OPCODE_PONG)


    def send(self, message, opcode=OPCODE_TEXT):
        """Send a frame over the websocket with message as its payload

        Keyword args:
        opcode -- the opcode to use (default OPCODE_TEXT)
        """

        if self.websocket_closed:
            raise Exception('Connection was terminated')

        if not self._is_valid_opcode(opcode):
            raise Exception('Invalid opcode %d' % opcode)

        if opcode == self.OPCODE_TEXT:
            message = self._encode_text(message)

        # TODO: implement masking
        # TODO: implement fragmented messages
        mask_bit = 0
        fin = 1
        masking_key = None

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

        if masking_key:
            self.socket.sendall(str(header + masking_key + mask(message))) # TODO: implement
        else:
            self.socket.sendall(header + message)


    def close(self, reason, message):
        """Close the websocket, sending the specified reason and message"""

        message = self._encode_text(message)
        self.send(struct.pack('!H%ds' % len(message), reason, message), opcode=self.OPCODE_CLOSE)
        self.websocket_closed = True

        # based on gevent/pywsgi.py
        # see http://pypi.python.org/pypi/gevent#downloads
        if self.socket is not None:
            try:
                self.socket._sock.close()
                self.socket.close()
            except socket.error:
                pass
