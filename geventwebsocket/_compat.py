import sys


PY3 = sys.version_info[0] == 3
PY2 = sys.version_info[0] == 2

if PY2:
    raise NotImplementedError(
        "This version of `gevent-websocket` does not support Python 2.x"
    )
else:
    text_type = str
    string_types = str,
    range_type = range
    # noinspection PyPep8
    iteritems = lambda x: iter(list(x.items()))
    # b = lambda x: codecs.latin_1_encode(x)[0]


def gevent_pywsgi_write(self, data):
    """
    Monkey-patched version of the `gevent.pywsgi.WSGIHandler.write` method that ensures
    that the passed `data` (which may be unicode string) are encoded to UTF8 bytes prior
    to being written.
    """

    if self.code in (304, 204) and data:
        raise self.ApplicationError('The %s response must have no body' % self.code)

    # Guard against unicode strings being concatenated with `bytes`.
    if isinstance(data, str):
        data = data.encode("utf-8")

    if self.headers_sent:
        self._write(data)
    else:
        if not self.status:
            raise self.ApplicationError("The application did not call start_response()")
        self._write_with_headers(data)
