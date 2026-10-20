#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")" || exit 1
python3 tvkit.py key off
code=$?
if [ "$code" != 0 ]; then printf "\nPress Return to close.\n"; read -r; fi
exit "$code"
