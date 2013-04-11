import inspect
import types
import json

from .base import BaseProtocol


def export_rpc(arg=None):
   if type(arg) is types.FunctionType:
      arg._rpc = arg.__name__
      return arg


class Prefixes(object):
    def __init__(self):
        self.prefixes = {}

    def add(self, prefix, uri):
        self.prefixes[prefix] = uri

    def resolve(self, curie_or_uri):
        if "http://" in curie_or_uri:
            return curie_or_uri
        elif ':' in curie_or_uri:
            prefix, proc = curie_or_uri.split(':', 1)
            return self.prefixes[prefix] + proc
        else:
            raise Exception(curie_or_uri)


class RemoteProcedures(object):
    def __init__(self):
        self.calls = {}

    def register_procedure(self, uri, proc):
        self.calls[uri] = proc

    def register_object(self, uri, obj):
        for k in inspect.getmembers(obj, inspect.ismethod):
            if '_rpc' in k[1].__dict__:
               proc_uri = uri + k[1]._rpc
               self.calls[proc_uri] = (obj, k[1])

    def call(self, uri, args):
        if uri in self.calls:
            proc = self.calls[uri]
            if isinstance(proc, tuple):
                return proc[1](proc[0](), *args)
            else:
                return self.calls[uri](*args)
        else:
            raise Exception("no such uri '{}'".format(uri))


class WampProtocol(BaseProtocol):
    MSG_WELCOME = 0;
    MSG_PREFIX = 1;
    MSG_CALL = 2;
    MSG_CALL_RESULT = 3;
    MSG_CALL_ERROR = 4;
    MSG_SUBSCRIBE = 5;
    MSG_UNSUBSCRIBE = 6;
    MSG_PUBLISH = 7;
    MSG_EVENT = 8;

    PROTOCOL_NAME = "wamp"

    def __init__(self, *args, **kwargs):
        self.procedures = RemoteProcedures()
        self.prefixes = Prefixes()
        self.session_id = "3434324"  # TODO generate

        super(WampProtocol, self).__init__(*args, **kwargs)

    def _serialize(self, data):
        return json.dumps(data)

    def register_procedure(self, *args, **kwargs):
        self.procedures.register_procedure(*args, **kwargs)

    def register_object(self, *args, **kwargs):
        self.procedures.register_object(*args, **kwargs)

    def send_welcome(self):
        from geventwebsocket import get_version

        welcome = [
            self.MSG_WELCOME,
            self.session_id,
            1,
            'gevent-websocket/' + get_version()
        ]
        self.app.ws.send(self._serialize(welcome))

    def on_open(self):
        self.app.on_open()

    def on_message(self, message):
        data = json.loads(message)

        if not isinstance(data, list):
            raise Exception('incoming data is no list')

        print "RX", data

        if data[0] == self.MSG_PREFIX and len(data) == 3:
            prefix, uri = data[1:3]
            self.prefixes.add(prefix, uri)

        if data[0] == self.MSG_CALL and len(data) >= 3:
            call_id, curie_or_uri = data[1:3]
            args = data[3:]

            if not isinstance(call_id, (str, unicode)):
                raise Exception()
            if not isinstance(curie_or_uri, (str, unicode)):
                raise Exception()

            uri = self.prefixes.resolve(curie_or_uri)

            try:
                result = self.procedures.call(uri, args)
                result_msg = [self.MSG_CALL_RESULT, call_id, result]
            except Exception, e:
                result_msg = [self.MSG_CALL_ERROR,
                              call_id, 'http://TODO#generic',
                              str(type(e)), str(e)]

            self.app.on_message(self._serialize(result_msg))

    def on_close(self):
        self.app.on_close()

