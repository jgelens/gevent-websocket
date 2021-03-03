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
