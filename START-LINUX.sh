#!/bin/sh
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Нужен Python 3.11 или новее: https://www.python.org/downloads/'
    exit 1
fi
exec python3 launch.py "$@"
