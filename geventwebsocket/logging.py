from logging import getLogger, StreamHandler, getLoggerClass, Formatter, DEBUG


# noinspection PyShadowingBuiltins
def create_logger(name, debug=False, format=None):
    Logger = getLoggerClass()

    # noinspection PyMethodParameters
    class DebugLogger(Logger):
        def getEffectiveLevel(x):
            if x.level == 0 and debug:
                return DEBUG
            else:
                return Logger.getEffectiveLevel(x)

    # noinspection PyMethodParameters
    class DebugHandler(StreamHandler):
        def emit(x, record):
            StreamHandler.emit(x, record) if debug else None

    handler = DebugHandler()
    handler.setLevel(DEBUG)

    if format:
        handler.setFormatter(Formatter(format))

    logger = getLogger(name)
    del logger.handlers[:]
    logger.__class__ = DebugLogger
    logger.addHandler(handler)

    return logger
