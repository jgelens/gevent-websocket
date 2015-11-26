import sys


PY2 = sys.version_info[0] == 2


if PY2:
    bytes = str
    text_type = unicode
    string_types = (str, unicode)
    range_type = xrange
    iteritems = lambda x: x.iteritems()
else:
    text_type = str
    string_types = (str,)
    range_type = range
    iteritems = lambda x: iter(x.items())
