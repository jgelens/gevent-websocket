VERSION = (0, 4, 0, 'alpha', 0)


def get_version(*args, **kwargs):
    from .utils import get_version
    return get_version(*args, **kwargs)
