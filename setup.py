from setuptools import setup, find_packages

setup(
    name="gevent-websocket",
    version="0.1.0",
    description="Websocket handler for the gevent pywsgi server, a Python network library",
    long_description=open("README.rst").read(),
    author="Jeffrey Gelens",
    author_email="jeffrey@noppo.pro",
    license="BSD",
    url="http://www.gelens.org/code/gevent-websocket/",
    download_url="http://www.gelens.org/code/gevent-websocket/",
    install_requires=("gevent", "greenlet"),
    packages=find_packages(exclude=["examples","tests"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers",
    ],
)
