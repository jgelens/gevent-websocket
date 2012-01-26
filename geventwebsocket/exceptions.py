from socket import error as socket_error


class WebSocketError(socket_error):
    pass


class FrameTooLargeException(WebSocketError):
    pass
