#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the vendor makefiles, then drop the generator's prefer flags and put
# them back only where a stock prebuilt has to displace the platform module of the
# same name. Only a cc prebuilt can do that: android/prebuilt.go is what makes
# prefer hide the source module, and prebuilt_etc is not built on it, so an etc
# path with two writers has to lose one of them at the blob list instead. And only
# where the platform module declares vendor or proprietary: it builds the source
# as system there, and checkInvariantsForSourceAndPrebuilt makes a mismatch a
# fatal "partition is different" rather than a duplicate path. A
# vendor_available platform module owns its vendor path and the blob goes. Nor can a
# module whose source links another interface version displace: the prebuilt's deps
# join the source's, one graph reaches both versions, and the version check stops.
# tools/preflight.py and tools/make_dupes.py check the result.
#

import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
VENDOR_BP = HERE / '../../../vendor/nubia/Z2577/Android.bp'
PREFER = re.compile(r'^    prefer: true,\n', re.M)

# prebuilts that keep the platform module name and take the platform's place
DISPLACE = (
    'libwifi-hal',
)

# A module that links the platform's libgralloctypes reaches the newer graphics
# common through it, and these three blobs link the V3 one themselves, so the
# graph holds two versions of one interface and Soong stops. Neither edge can go
# the other way: the V3 soname is what the blobs load, and the camera and codec2
# blobs keep the platform library installed. So the helper edge is dropped here
# and the blobs resolve it at runtime, where there is one copy anyway.
DROP_SHARED = {
    'android.hardware.graphics.mapper@4.0-impl-arm': ('libgralloctypes',),
    'android.hardware.graphics.allocator@4.0-impl-arm': ('libgralloctypes',),
    'libGLES_mali': ('libgralloctypes',),
}


def block_bounds(lines, name):
    """(name line, closing brace) of the module block called `name`."""
    for index, line in enumerate(lines):
        if line.strip() == f'name: "{name}",':
            end = index
            while end < len(lines) and lines[end].rstrip() != '}':
                end += 1
            return index, end
    return None, None


def drop_shared(lines, name, libs):
    """Remove named shared_libs entries from one module block."""
    name_line, end = block_bounds(lines, name)
    if name_line is None:
        raise SystemExit(f'no module named {name} in {VENDOR_BP}')
    names = {f'"{lib}",' for lib in libs}
    dropped = 0
    for index in range(end, name_line, -1):
        if lines[index].strip() in names:
            del lines[index]
            dropped += 1
    return dropped


def add_prefer(lines, name):
    """Give one prebuilt the prefer flag, once."""
    name_line, end = block_bounds(lines, name)
    if name_line is None:
        raise SystemExit(f'no module named {name} in {VENDOR_BP}')
    if any('prefer:' in line for line in lines[name_line:end]):
        return False
    lines.insert(name_line + 1, '    prefer: true,')
    return True


subprocess.run(
    [str(HERE / 'extract-files.py'), '--regenerate_makefiles'],
    check=True,
)

bp = VENDOR_BP.resolve()
text, count = PREFER.subn('', bp.read_text())

lines = text.splitlines()
preferred = sum(add_prefer(lines, name) for name in DISPLACE)
dropped = sum(
    drop_shared(lines, name, libs) for name, libs in DROP_SHARED.items()
)
bp.write_text('\n'.join(lines) + '\n')

if count:
    print(f'dropped {count} prefer: true lines from {bp}')
if preferred:
    print(f'{preferred} prefer flags put back in {bp}')
if dropped:
    print(f'{dropped} shared_libs entries dropped from {bp}')
