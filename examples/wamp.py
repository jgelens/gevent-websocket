from geventwebsocket.server import WebSocketServer
from geventwebsocket.resource import MessageResource, WebSocketApplication
from geventwebsocket.protocols.wamp import WampProtocol, export_rpc


class RPCTestClass(object):
    @export_rpc
    def mult(self, x, y):
        return x * y


class WampApplication(WebSocketApplication):
    def on_open(self):
        self.wamp.register_procedure("http://localhost:8000/calc#add", self.add)
        self.wamp.register_object("http://localhost:8000/test#", RPCTestClass)
        self.wamp.send_welcome()
        print "opened"

    def on_message(self, message):
        print "message: ", message
        super(WampApplication, self).on_message(message)

    def on_close(self):
        print "closed"

    def add(self, var, has):
        has.update({'bloep': var})
        return has

    def build_protocol(self):
        self.wamp = WampProtocol(self)
        return self.wamp

    @classmethod
    def supported_protocols(cls):
        return [WampProtocol.PROTOCOL_NAME]


if __name__ == "__main__":
    resource = MessageResource(apps={
        '/': WampApplication
    })

    server = WebSocketServer(("", 8000), resource, protocols=resource.supported_protocols,  debug=True)
    server.serve_forever()
