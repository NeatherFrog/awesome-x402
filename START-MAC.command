#!/bin/sh
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Нужен Python 3.11 или новее: https://www.python.org/downloads/'
    printf '%s\n' 'Нажмите Enter, чтобы закрыть окно.'
    read -r TRADING_UNUSED_INPUT
    exit 1
fi
python3 launch.py "$@"
TRADING_EXIT_CODE=$?
if [ "$TRADING_EXIT_CODE" -ne 0 ]; then
    printf '%s\n' 'Нажмите Enter, чтобы закрыть окно.'
    read -r TRADING_UNUSED_INPUT
fi
exit "$TRADING_EXIT_CODE"
