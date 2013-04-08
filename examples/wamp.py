from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.protocols.wamp import WampProtocol, export_rpc


class RPCTestClass(object):
    @export_rpc
    def mult(self, x, y):
        return x * y


class AdditionServer(WampProtocol):
    def on_open(self):
        self.register_procedure("http://localhost:8000/calc#add", self.add)
        self.register_object("http://localhost:8000/test#", RPCTestClass)

    def add(self, var, has):
        has.update({'bloep': var})
        return has


def app(environ, start_response):
    AdditionServer(environ)

if __name__ == "__main__":
    server = pywsgi.WSGIServer(("", 8000), app, handler_class=WebSocketHandler)
    server.serve_forever()
