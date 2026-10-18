#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the vendor makefiles, then drop the generator's prefer flags and put
# them back only where a stock prebuilt has to displace the platform module of the
# same name. Only a cc prebuilt can do that: android/prebuilt.go is what makes
# prefer hide the source module, and prebuilt_etc is not built on it, so an etc
# path with two writers has to lose one of them at the blob list instead.
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
    'libkeymint',
    'lib_android_keymaster_keymint_utils',
    'libwifi-hal',
    'android.hardware.graphics.common-V3-ndk',
    'android.hardware.graphics.allocator-V1-ndk',
    'android.media.audio.common.types-V1-cpp',
    'wpa_supplicant',
    'hostapd',
)


def block_bounds(lines, name):
    """(name line, closing brace) of the module block called `name`."""
    for index, line in enumerate(lines):
        if line.strip() == f'name: "{name}",':
            end = index
            while end < len(lines) and lines[end].rstrip() != '}':
                end += 1
            return index, end
    return None, None


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
bp.write_text('\n'.join(lines) + '\n')

if count:
    print(f'dropped {count} prefer: true lines from {bp}')
if preferred:
    print(f'{preferred} prefer flags put back in {bp}')
