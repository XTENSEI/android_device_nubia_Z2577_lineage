#!/usr/bin/env -S PYTHONPATH=../../../tools/extract-utils python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

from extract_utils.fixups_lib import (
    lib_fixups,
    lib_fixups_user_type,
)
from extract_utils.main import (
    ExtractUtils,
    ExtractUtilsModule,
)

namespace_imports = [
    'device/nubia/Z2577',
]

lib_fixups: lib_fixups_user_type = {
    **lib_fixups,
    'libdav1d': lambda lib, partition: 'libdav1d_vendor',
    'libskia': lambda lib, partition: 'libskia_vendor',
    'android.hardware.boot@1.0-impl-1.2':
        lambda lib, partition: 'android.hardware.boot@1.2-impl',
    'libtensorflowlite_jni':
        lambda lib, partition: 'libtensorflowlite_jni_odm'
        if partition == 'odm' else 'libtensorflowlite_jni_vendor',
    'libvibrator': lambda lib, partition: 'libvibrator_vendor',
}

module = ExtractUtilsModule(
    'Z2577',
    'nubia',
    lib_fixups=lib_fixups,
    namespace_imports=namespace_imports,
)

if __name__ == '__main__':
    utils = ExtractUtils.device(module)
    utils.run()
