#!/usr/bin/env python

from setuptools import setup

with open("README.md", "rt") as fh:
    long_description = fh.read()

dependencies = [
    "chia-blockchain@git+https://github.com/Chia-Network/chia-blockchain.git@protocol_and_cats_rebased#23d571d9bb6b5003b49dee7ee31c1799358c5349",
    "requests"
]

dev_dependencies = [
    "black",
]

setup(
    name="singleton-utils",
    version="0.0.1",
    author="xch-gallery",
    setup_requires=["setuptools_scm"],
    install_requires=dependencies,
    extras_require=dict(
        dev=dev_dependencies,
    ),
    project_urls={
        "Bug Reports": "https://github.com/xch-gallery/singleton-utils",
        "Source": "https://github.com/xch-gallery/singleton-utils",
    },
)
