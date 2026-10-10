#!/bin/bash
# Refuse to start a build while a prebuilt name is still shadowed.
set -e
here=$(dirname "$(readlink -f "$0")")

if [ ! -f build/envsetup.sh ]; then
    echo "run this from the source root" >&2
    exit 2
fi

python3 "$here/shadow_sweep.py" --top "$PWD" --gate

. build/envsetup.sh
m "$@"
