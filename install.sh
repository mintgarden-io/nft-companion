#!/bin/bash

python3 -m venv venv
. ./venv/bin/activate

python3 -m pip install --upgrade pip

pip3 install wheel && pip3 install -r requirements.txt

deactivate