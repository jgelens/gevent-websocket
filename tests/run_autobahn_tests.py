#!/usr/bin/env python
"""Test gevent-websocket with the test suite of Autobahn

    http://www.tavendo.de/autobahn/testsuite.html
"""
import sys
import os
import subprocess
import time
import urllib2
from twisted.python import log
from twisted.internet import reactor
from autobahn.fuzzing import FuzzingClientFactory


spec = {
   "options": {"failByDrop": False},
   "enable-ssl": False,
   "servers": []}


default_args = ["*",
         "x7.5.1",
         "x7.9.3",
         "x7.9.4",
         "x7.9.5",
         "x7.9.6",
         "x7.9.7",
         "x7.9.8",
         "x7.9.9",
         "x7.9.10",
         "x7.9.11",
         "x7.9.12",
         "x7.9.13"]
# We ignore 7.5.1 because it checks that close frame has valid utf-8 message
# we do not validate utf-8.

# We ignore 7.9.3-13 because it checks that when a close frame with code 1004
# and others sent, 1002 is sent back; we only send back 1002 for obvious
# violations like < 1000 and >= 5000; for all codes in the 1000-5000 range
# we send code 1000 back


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
    parser.add_option('--autobahn', default='../../src/Autobahn/testsuite/websockets/servers/test_autobahn.py')
    options, args = parser.parse_args()

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

    if options.autobahn and not os.path.exists(options.autobahn):
        print 'Ignoring %s (not found)' % options.autobahn
        options.autobahn = None
    pool = ProcessPool()
    try:
        if options.geventwebsocket:
            pool.spawn([sys.executable, options.geventwebsocket])
        if options.autobahn:
            pool.spawn([sys.executable, options.autobahn])
        pool.wait(1)
        if options.geventwebsocket:
            agent = urllib2.urlopen('http://127.0.0.1:7000/version').read().strip()
            assert agent and '\n' not in agent and 'gevent-websocket' in agent, agent
            spec['servers'].append({"url": "ws://localhost:7000",
                                    "agent": agent,
                                    "options": {"version": 17}})
        if options.autobahn:
            spec['servers'].append({'url': 'ws://localhost:9000/',
                                    'agent': 'AutobahnServer',
                                    'options': {'version': 17}})
        log.startLogging(sys.stdout)
        FuzzingClientFactory(spec)
        reactor.run()
    finally:
        pool.kill()
