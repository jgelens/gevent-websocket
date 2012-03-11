import sys


if sys.version_info[:2] == (2, 7):
    # Python 2.7 has a working BufferedReader but socket.makefile() does not
    # use it.
    # Python 2.6's BufferedReader is broken (TypeError: recv_into() argument
    # 1 must be pinned buffer, not bytearray).
    from io import BufferedReader, RawIOBase

    class SocketIO(RawIOBase):
        def __init__(self, sock):
            RawIOBase.__init__(self)
            self._sock = sock

        def readinto(self, b):
            self._checkClosed()
            while True:
                try:
                    return self._sock.recv_into(b)
                except socket_error as ex:
                    if ex.args[0] == EINTR:
                        continue
                    raise

        def readable(self):
            return self._sock is not None

        @property
        def closed(self):
            return self._sock is None

        def fileno(self):
            self._checkClosed()
            return self._sock.fileno()

        @property
        def name(self):
            if not self.closed:
                return self.fileno()
            else:
                return -1

        def close(self):
            if self._sock is None:
                return
            else:
                self._sock.close()
                self._sock = None
                RawIOBase.close(self)

    def makefile(socket):
        return BufferedReader(SocketIO(socket))

else:
    def makefile(socket):
        # XXX on python3 enable buffering
        return socket.makefile()


if sys.version_info[:2] < (2, 7):
    def is_closed(fobj):
        return fobj._sock is None
else:
    def is_closed(fobj):
        return fobj.closed
