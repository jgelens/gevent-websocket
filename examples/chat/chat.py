import json

from gevent import monkey
monkey.patch_all()

from flask import Flask, app, render_template
from werkzeug.debug import DebuggedApplication

from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

flask_app = Flask(__name__)
flask_app.debug = True


class ChatApplication(WebSocketApplication):
    def on_open(self):
        print "Some client connected!"

    def on_message(self, message):
        if message is None:
            return

        message = json.loads(message)

        if message['msg_type'] == 'message':
            self.broadcast(message)
        elif message['msg_type'] == 'update_clients':
            self.send_client_list(message)

    def send_client_list(self, message):
        current_client = self.ws.handler.active_client
        current_client.nickname = message['nickname']

        self.ws.send(json.dumps({
            'msg_type': 'update_clients',
            'clients': [
                getattr(client, 'nickname', 'anonymous')
                for client in self.ws.handler.server.clients.values()
            ]
        }))

    def broadcast(self, message):
        for client in self.ws.handler.server.clients.values():
            client.ws.send(json.dumps({
                'msg_type': 'message',
                'nickname': message['nickname'],
                'message': message['message']
            }))

    def on_close(self, reason):
        print "Connection closed! "


@flask_app.route('/')
def index():
    return render_template('index.html')

WebSocketServer(
    ('0.0.0.0', 8000),

    Resource({
        '^/chat': ChatApplication,
        '^/.*': DebuggedApplication(flask_app)
    }),

    debug=False
).serve_forever()
