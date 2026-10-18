#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the vendor makefiles, then two fixes the generator has no flag for.
# A prebuilt that claims an AOSP module of the same name on another partition is
# what Soong rejects, so the prefer flags go. Where the stock copy has to win its
# path, the prebuilt displaces the platform module with overrides instead of
# installing beside it. tools/preflight.py and tools/make_dupes.py check both.
#

import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
VENDOR_BP = HERE / '../../../vendor/nubia/Z2577/Android.bp'
VENDOR_MK = HERE / '../../../vendor/nubia/Z2577/Z2577-vendor.mk'
PREFER = re.compile(r'^    prefer: true,\n', re.M)

# our module, then the platform module it has to displace
OVERRIDES = {
    'libkeymint_vendor': 'libkeymint',
    'lib_android_keymaster_keymint_utils_vendor':
        'lib_android_keymaster_keymint_utils',
    'libwifi-hal_vendor': 'libwifi-hal',
    'wpa_supplicant_vendor': 'wpa_supplicant',
    'hostapd_vendor': 'hostapd',
    'identity-default.xml_vendor': 'identity-default.xml',
}

# an etc name cannot carry ;MODULE=, so the rename happens here instead
RENAMES = {
    'identity-default.xml': 'identity-default.xml_vendor',
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


def add_overrides(lines, ours, platform):
    """Put overrides on our block, once."""
    name_line, end = block_bounds(lines, ours)
    if name_line is None:
        raise SystemExit(f'no module named {ours} in {VENDOR_BP}')
    if any('overrides:' in line for line in lines[name_line:end]):
        return False
    lines.insert(name_line + 1, f'    overrides: ["{platform}"],')
    return True


def rename(lines, old, new):
    """Rename one etc module to a name of its own."""
    name_line, _ = block_bounds(lines, old)
    if name_line is None:
        raise SystemExit(f'no module named {old} in {VENDOR_BP}')
    lines[name_line] = f'    name: "{new}",'
    return True


subprocess.run(
    [str(HERE / 'extract-files.py'), '--regenerate_makefiles'],
    check=True,
)

bp = VENDOR_BP.resolve()
text, count = PREFER.subn('', bp.read_text())

lines = text.splitlines()
renamed = 0
for old, new in RENAMES.items():
    rename(lines, old, new)
    renamed += 1
overridden = 0
for ours, platform in OVERRIDES.items():
    overridden += add_overrides(lines, ours, platform)
bp.write_text('\n'.join(lines) + '\n')

mk = VENDOR_MK.resolve()
mk_text = mk.read_text()
for old, new in RENAMES.items():
    mk_text = mk_text.replace(f'    {old} \\\n', f'    {new} \\\n')
mk.write_text(mk_text)

if count:
    print(f'dropped {count} prefer: true lines from {bp}')
if renamed or overridden:
    print(f'{renamed} renamed, {overridden} overrides in {bp}')
