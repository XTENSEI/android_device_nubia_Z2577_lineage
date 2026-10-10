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

# The tool's own fixups, without which the generated shared_libs keep the blob's
# soname: the arch suffixed clang runtimes and the protobuf vendorcompat pair
#
# libdav1d: the platform builds it static only, so the shared copy the vendor
# blobs need carries its own module name and they are repointed here
# libskia: the platform builds it static and core only, so a vendor shared copy
# needs a name of its own and the dependants are repointed here
lib_fixups: lib_fixups_user_type = {
    **lib_fixups,
    'libdav1d': lambda lib, partition: 'libdav1d_vendor',
    'libskia': lambda lib, partition: 'libskia_vendor',
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
