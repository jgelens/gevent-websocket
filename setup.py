from setuptools import setup, find_packages


version = __import__('geventwebsocket').get_version()

setup(
    name="gevent-websocket",
    version=version,
    url="https://www.gitlab.com/noppo/gevent-websocket",
    author="Jeffrey Gelens",
    author_email="jeffrey@noppo.pro",
    description=("Websocket handler for the gevent pywsgi server, a Python "
                 "network library"),
    long_description=open("README.rst").read(),
    download_url="https://www.gitlab.com/noppo/gevent-websocket",
    packages=find_packages(exclude=["examples", "tests"]),
    license=open('LICENSE').read(),
    zip_safe=False,
    install_requires=("gevent"),
    classifiers=[
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ]
)
