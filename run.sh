#!/bin/sh
# Run from any directory; weekly.py reads the configured dotenv file.
set -eu
umask 077
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$task_dir/weekly.py" --config "$task_dir/config.json" "$@"
