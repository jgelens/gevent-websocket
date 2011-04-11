from gevent.coros import Semaphore

# This class implements the Websocket protocol draft version as of May 23, 2010
# The version as of August 6, 2010 will be implementend once Firefox or
# Webkit-trunk support this version.

class WebSocket(object):
    def __init__(self, sock, rfile, environ):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self._writelock = Semaphore(1)

    def send(self, message):
        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif isinstance(message, str):
            message = unicode(message).encode('utf-8')
        else:
            raise Exception("Invalid message encoding")

        with self._writelock:
            self.socket.sendall("\x00" + message + "\xFF")

    def detach(self):
        self.socket = None
        self.rfile = None
        self.handler = None

    def close(self):
        # TODO implement graceful close with 0xFF frame
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass
            self.detach()


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

    def receive(self):
        while self.socket is not None:
            frame_str = self.rfile.read(1)
            if not frame_str:
                # Connection lost?
                self.close()
                break
            else:
                frame_type = ord(frame_str)


            if (frame_type & 0x80) == 0x00: # most significant byte is not set
                if frame_type == 0x00:
                    bytes = self._read_until()
                    return bytes.decode("utf-8", "replace")
                else:
                    self.close()
            elif (frame_type & 0x80) == 0x80: # most significant byte is set
                # Read binary data (forward-compatibility)
                if frame_type != 0xff:
                    self.close()
                    break
                else:
                    length = self._message_length()
                    if length == 0:
                        self.close()
                        break
                    else:
                        self.rfile.read(length) # discard the bytes
            else:
                raise IOError("Reveiced an invalid message")
