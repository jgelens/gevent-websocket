from .exceptions import WebSocketError


class WebSocketApplication(object):
    def __init__(self, ws):
        self.protocol = self.build_protocol()
        self.ws = ws

    def handle(self):
        self.protocol.on_open()

        while True:
            try:
                message = self.ws.receive()
            except WebSocketError:
                break

            if message is None:
                self.protocol.on_close()
                break
            else:
                self.protocol.on_message(message)

    def on_open(self, *args, **kwargs):
        pass

    def on_close(self, *args, **kwargs):
        pass

    def on_message(self, message, *args, **kwargs):
        self.ws.send(message, **kwargs)

    @classmethod
    def protocol(self):
        return ''


class Resource(object):
    def __init__(self, environ=None, apps=[]):
        self.environ = environ
        self.ws = None
        self.apps = apps
        self.current_app = None

    def app_protocol(self, path):
        if path in self.apps:
            return self.apps[path].protocol()
        else:
            return ''

    def listen(self):
        self.ws = self.environ['wsgi.websocket']

        if self.ws.path in self.apps:
            self.current_app = self.apps[self.ws.path](self.ws)

        if self.current_app:
            self.current_app.ws = self.ws
            self.current_app.handle()
        else:
            raise Exception("No apps defined")

    def __call__(self, environ, start_response):
        self.environ = environ
        self.listen()
