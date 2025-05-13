#!/bin/bash
python -m pip install --upgrade pip
pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/pw-browsers" python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/pw-browsers" python -m playwright install-deps