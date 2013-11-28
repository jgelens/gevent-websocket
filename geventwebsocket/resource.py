from .protocols.base import BaseProtocol
from .exceptions import WebSocketError


class WebSocketApplication(object):
    protocol_class = BaseProtocol

    def __init__(self, ws):
        self.protocol = self.protocol_class(self)
        self.ws = ws

    def handle(self):
        self.protocol.on_open()

        while True:
            try:
                message = self.ws.receive()
            except WebSocketError:
                self.protocol.on_close()

            self.protocol.on_message(message)

    def on_open(self, *args, **kwargs):
        pass

    def on_close(self, *args, **kwargs):
        pass

    def on_message(self, message, *args, **kwargs):
        self.ws.send(message, **kwargs)

    @classmethod
    def protocol_name(cls):
        return cls.protocol_class.PROTOCOL_NAME


class Resource(object):
    def __init__(self, apps=None, environ=None):
        self.environ = environ
        self.ws = None
        self.apps = apps if apps else []
        self.current_app = None

    def app_protocol(self, path):
        if path in self.apps:
            return self.apps[path].protocol_name()
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

    def run_app(self, environ, start_response):
        if self.environ['PATH_INFO'] in self.apps:
            return self.apps[self.environ['PATH_INFO']](environ, start_response)
        else:
            raise Exception("No apps defined")

    def __call__(self, environ, start_response):
        self.environ = environ

        if 'wsgi.websocket' in self.environ:
            self.listen()

            return None
        else:
            return self.run_app(environ, start_response)
