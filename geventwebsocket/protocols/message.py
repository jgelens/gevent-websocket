class MessageProtocol(object):
    def __init__(self, environ, interfaces):
        self.ws = environ['wsgi.websocket']
        self.interfaces = interfaces

        if self.ws.path in interfaces.keys():
            self.active_interface = interfaces[self.ws.path]
        else:
            raise Exception("no interface found")

        self.on_open()
        self._handle()

    def _handle(self):
        while True:
            message = self.ws.receive()

            if message is None:
                self.active_interface.on_close()
                break
            else:
                self.active_interface.on_message(message)

