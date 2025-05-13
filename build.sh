#!/bin/bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install --with-deps chromium