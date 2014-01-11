from geventwebsocket.server import WebSocketServer
from geventwebsocket.resource import Resource, WebSocketApplication
from geventwebsocket.protocols.wamp import WampProtocol, export_rpc


db = {}

class KeyValue(object):
    @export_rpc
    def set(self, key, val):
        db[key] = val

    @export_rpc
    def get_val(self, key):
        return db.get(key)


class WampApplication(WebSocketApplication):
    protocol_class = WampProtocol

    def on_open(self):
        wamp = self.protocol
        wamp.register_procedure("http://localhost:8000/calc#add", self.add)
        wamp.register_object("http://localhost:8000/db#", KeyValue())
        print "opened"

    def on_message(self, message):
        print "message: ", message
        super(WampApplication, self).on_message(message)

    def on_close(self, reason):
        print "closed"

    def add(self, x, y):
        return int(x) + int(y)


def static_wsgi_app(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/html")])
    return open("wamp_example.html").readlines()

if __name__ == "__main__":
    resource = Resource({
        '^/wamp_example$': WampApplication,
        '^/$': static_wsgi_app
    })

    server = WebSocketServer(("", 8000), resource, debug=True)
    server.serve_forever()
