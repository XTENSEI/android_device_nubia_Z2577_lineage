#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
VENDOR_BP = HERE / '../../../vendor/nubia/Z2577/Android.bp'
PREFER = re.compile(r'^    prefer: true,\n', re.M)

DISPLACE = (
    'libwifi-hal',
)

DROP_SHARED = {
    'android.hardware.graphics.mapper@4.0-impl-arm':
        ('libgralloctypes', 'libnativewindow'),
    'android.hardware.graphics.allocator@4.0-impl-arm':
        ('libgralloctypes', 'libnativewindow'),
    'libGLES_mali': (
        'libgralloctypes', 'libnativewindow',
        'android.hardware.graphics.common-V3-ndk',
    ),
    'android.hardware.neuralnetworks@aidl-service-armnn-gpu':
        ('libui', 'libnativewindow'),
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
