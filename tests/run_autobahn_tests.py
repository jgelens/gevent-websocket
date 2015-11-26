#!/usr/bin/env python
"""
Test gevent-websocket with the test suite of Autobahn
http://autobahn.ws/testsuite
"""

import click
import requests
import sys
import subprocess
import time

from twisted.python import log
from twisted.internet import reactor
from autobahntestsuite.fuzzing import FuzzingClientFactory


spec = {
    "options": {"failByDrop": False},
    "enable-ssl": False,
    "servers": []
}

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
            self.check()
            if time.time() > end:
                break

    def kill(self):
        while self.popens:
            popen = self.popens.pop()
            try:
                popen.kill()
            except Exception as ex:
                print(ex)


@click.command()
@click.argument('server', default='examples/echoserver.py')
@click.option('--no-spawn', is_flag=True, default=False)
def main(server, no_spawn):
    spec['cases'] = ['*']
    spec['exclude-cases'] = []

    pool = ProcessPool()

    try:
        if not no_spawn:
            pool.spawn([sys.executable, server])
            pool.wait(1)

        response = requests.get('http://127.0.0.1:8000/version')
        agent = response.text.strip()

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


if __name__ == '__main__':
    main()
