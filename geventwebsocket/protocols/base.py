
class BaseProtocol(object):
    PROTOCOL_NAME = ""

    def __init__(self, app):
        self._app = app

    def on_open(self):
        self.app.on_open()

    def on_message(self, message):
        self.app.on_message(message)

    def on_close(self):
        self.app.on_close()

    @property
    def app(self):
        if self._app:
            return self._app
        else:
            raise Exception("No application coupled")

