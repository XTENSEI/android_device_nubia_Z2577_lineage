#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the vendor makefiles, then drop the prebuilt prefer flags. A
# prebuilt that claims an AOSP module of the same name on another partition is
# what Soong rejects, and where the platform builds a vendor variant that copy
# is the right one anyway. scratch/preflight.py checks the result.
#

import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
VENDOR_BP = HERE / '../../../vendor/nubia/Z2577/Android.bp'
PREFER = re.compile(r'^    prefer: true,\n', re.M)

subprocess.run(
    [str(HERE / 'extract-files.py'), '--regenerate_makefiles'],
    check=True,
)

bp = VENDOR_BP.resolve()
text = bp.read_text()
text, count = PREFER.subn('', text)
bp.write_text(text)

if count:
    print(f'dropped {count} prefer: true lines from {bp}')
