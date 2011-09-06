# This class implements the Websocket protocol draft version as of May 23, 2010
# The version as of August 6, 2010 will be implementend once Firefox or
# Webkit-trunk support this version.

import struct

class WebSocket(object):
    def __init__(self, sock, rfile, environ):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self.websocket_closed = False

    def send(self, message):
        if self.websocket_closed:
            raise Exception("Connection was terminated")

        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif isinstance(message, str):
            message = unicode(message).encode('utf-8')
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
        # TODO: buildin security agains lengths greater than 2**31 or 2**32
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

    def wait(self):
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

class WebSocketVersion7(WebSocket):
    FIN = int("10000000", 2)
    RSV = int("01110000", 2)
    OPCODE = int("00001111", 2)
    MASK = int("10000000", 2)
    PAYLOAD = int("01111111", 2)

    OPCODE_FRAG = 0x0
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
        self.compatibility_mode = compatibility_mode
        self._fragments = []

    def _read_from_socket(self, count):
        return self.rfile.read(count)

    # TODO: replace all magic numbers with constants
    def wait(self):
        while True:
            payload = ''
            if self.websocket_closed:
                return None

            opcode_octet, length_octet = struct.unpack('!BB', self._read_from_socket(2))

            if self.RSV & opcode_octet:
                self.close(self.REASON_PROTOCOL_ERROR, 'Reserved bits cannot be set')
                return None

            opcode = opcode_octet & self.OPCODE
            is_final_frag = (self.FIN & opcode_octet) != 0

            if self._is_opcode_invalid(opcode):
                self.close(self.REASON_PROTOCOL_ERROR, 'Invalid opcode %x' % opcode)
                return None
            
            if not is_final_frag and self.OPCODE_CLOSE <= opcode <= self.OPCODE_PONG:
                self.close(self.REASON_PROTOCOL_ERROR, 'Control frames cannot be fragmented')
                return None

            if len(self._fragments) > 0 and not is_final_frag and opcode != self.OPCODE_FRAG:
                self.close(self.REASON_PROTOCOL_ERROR,
                        'Received new fragment frame with non-zero opcode')
                return None

            if len(self._fragments) > 0 and is_final_frag and (
                    self.OPCODE_TEXT <= opcode <= self.OPCODE_BINARY):
                self.close(self.REASON_PROTOCOL_ERROR,
                        'Received new unfragmented data frame during fragmented message')
                return None

            if not self.MASK & length_octet:
                self.close(self.REASON_PROTOCOL_ERROR, 'MASK must be set')
                return None

            length_code = length_octet & self.PAYLOAD

            if length_code >= self.LEN_16 and (self.OPCODE_CLOSE <= opcode <= self.OPCODE_PONG):
                self.close(self.REASON_PROTOCOL_ERROR,
                        'Control frame payload cannot be larger than 125 bytes')
                return None

            if length_code < self.LEN_16:
                length = length_code
            elif length_code == self.LEN_16:
                length = struct.unpack('!H', self._read_from_socket(2))[0]
            elif length_code == self.LEN_64:
                length = struct.unpack('!Q', self._read_from_socket(8))[0]
            else:
                raise Exception('Calculated invalid length')

            mask_octets = struct.unpack('!BBBB', self._read_from_socket(4))
            masked_payload = self._read_from_socket(length)

            payload = ''

            j = 0
            for c in masked_payload:
                # TODO: optimize me? http://www.skymind.com/~ocrow/python_string/
                payload += chr(ord(c) ^ mask_octets[j])
                j = (j + 1) % 4

            if opcode == self.OPCODE_TEXT:
                payload = payload.decode('utf-8')
            elif opcode == self.OPCODE_CLOSE:
                if length >= 2:
                    reason, message = struct.unpack('!H%ds' % (length - 2), payload)
                else:
                    reason = message = None

                self.close(self.REASON_NORMAL, '')
                if not self.compatibility_mode:
                    return (reason, message)
                else:
                    return None

            if opcode == self.OPCODE_PING:
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

            if is_final_frag:
                payload = ''.join(self._fragments) + payload
                self._fragments = []
                return payload
            else:
                self._fragments.append(payload)

    def _encode_text(self, s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        elif isinstance(s, str):
            return unicode(s).encode('utf-8')
        else:
            raise Exception('Invalid encoding')

    def _is_opcode_invalid(self, opcode):
        return opcode < self.OPCODE_FRAG or (opcode > self.OPCODE_BINARY and 
                opcode < self.OPCODE_CLOSE) or opcode > self.OPCODE_PONG

    def send(self, message, opcode=OPCODE_TEXT):
        if self.websocket_closed:
            raise Exception('Connection was terminated')

        if self._is_opcode_invalid(opcode):
            raise Exception('Invalid opcode %d' % opcode)

        if opcode == self.OPCODE_TEXT:
            message = self._encode_text(message)

        length = len(message)

        if opcode == self.OPCODE_TEXT:
            message = struct.pack('!%ds' % length, message)

        if length < self.LEN_16:
            preamble = struct.pack('!BB', self.FIN | opcode, length)
        elif length < 2 ** 16:
            preamble = struct.pack('!BBH', self.FIN | opcode, self.LEN_16, length)
        elif length < 2 ** 64:
            preamble = struct.pack('!BBQ', self.FIN | opcode, self.LEN_64, length)
        else:
            # this can't really happen, but for correctness sake...
            raise Exception('Message is too long')

        self.socket.sendall(preamble + message)

    def close(self, reason, message):
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
