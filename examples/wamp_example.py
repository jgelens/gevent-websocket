from geventwebsocket.server import WebSocketServer
from geventwebsocket.resource import Resource, WebSocketApplication
from geventwebsocket.protocols.wamp import WampProtocol, export_rpc


class RPCTestClass(object):
    @export_rpc
    def mult(self, x, y):
        return x * y


class WampApplication(WebSocketApplication):
    protocol_class = WampProtocol

    def on_open(self):
        wamp = self.protocol
        wamp.register_procedure("http://localhost:8000/calc#add", self.add)
        wamp.register_object("http://localhost:8000/test#", RPCTestClass())
        wamp.register_pubsub("http://localhost:8000/somechannel")

        print "opened"

    def on_message(self, message):
        print "message: ", message
        super(WampApplication, self).on_message(message)

    def on_close(self, reason):
        print "closed"

    def add(self, var1, var2):
        return var1 + var2


def static_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return open("wamp_example.html").readlines()

if __name__ == "__main__":
    resource = Resource({
        '/page': static_wsgi_app,
        '/': WampApplication
    })

    server = WebSocketServer(("", 8000), resource, debug=True)
    server.serve_forever()
