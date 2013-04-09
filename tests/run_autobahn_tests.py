#!/usr/bin/env python
"""
Test gevent-websocket with the test suite of Autobahn
http://autobahn.ws/testsuite
"""
import sys
import subprocess
import time
import urllib2
from twisted.python import log
from twisted.internet import reactor
from autobahntestsuite.fuzzing import FuzzingClientFactory

spec = {
   "options": {"failByDrop": False},
   "enable-ssl": False,
   "servers": []}

default_args = ['*']


class ProcessPool(object):
    def __init__(self):
        self.popens = []

    def spawn(self, *args, **kwargs):
        popen = subprocess.Popen(*args, **kwargs)
        self.popens.append(popen)
        time.sleep(0.2)
        self.check()
        return popen

    def check(self):
        for popen in self.popens:
            if popen.poll() is not None:
                sys.exit(1)

    def wait(self, timeout):
        end = time.time() + timeout
        while True:
            time.sleep(0.1)
            pool.check()
            if time.time() > end:
                break

    def kill(self):
        while self.popens:
            popen = self.popens.pop()
            try:
                popen.kill()
            except Exception, ex:
                print ex


if __name__ == '__main__':
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--geventwebsocket', default='../examples/echoserver.py')
    options, args = parser.parse_args()

    # Load cases
    cases = []
    exclude_cases = []

    for arg in (args or default_args):
        if arg.startswith('x'):
            arg = arg[1:]
            exclude_cases.append(arg)
        else:
            cases.append(arg)

    spec['cases'] = cases
    spec['exclude-cases'] = exclude_cases

    pool = ProcessPool()

    try:
        if options.geventwebsocket:
            pool.spawn([sys.executable, options.geventwebsocket])

        pool.wait(1)

        if options.geventwebsocket:
            agent = urllib2.urlopen('http://127.0.0.1:8000/version').read().strip()

            assert agent and '\n' not in agent and 'gevent-websocket' in agent, agent

            spec['servers'].append({"url": "ws://localhost:8000",
                                    "agent": agent,
                                    "options": {"version": 18}})

        log.startLogging(sys.stdout)

        # Start testing the server using the FuzzingClient
        FuzzingClientFactory(spec)

        reactor.run()
    finally:
        pool.kill()
