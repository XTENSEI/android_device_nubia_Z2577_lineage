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
    'libkeymint': lambda lib, partition: 'libkeymint_vendor',
    'lib_android_keymaster_keymint_utils':
        lambda lib, partition: 'lib_android_keymaster_keymint_utils_vendor',
    # the stock boot service links the stock impl; the platform's
    # android.hardware.boot@1.2-impl installs the same hw/ file name
    'android.hardware.boot@1.0-impl-1.2':
        lambda lib, partition: 'android.hardware.boot@1.2-impl',
    # the audio types the stock blobs link at V1: the platform supplies V4 down
    # the libstagefright_foundation chain, and one variant may not carry two
    # versions of the same aidl_interface
    'android.media.audio.common.types-V1-cpp':
        lambda lib, partition: 'android.media.audio.common.types-V1-cpp_vendor',
    # same rule for the graphics interfaces, where the platform reaches V7 and V2
    # into the same variants through libgralloctypes and the mapper, and the stock
    # blobs link V3 and V1
    'android.hardware.graphics.common-V3-ndk':
        lambda lib, partition: 'android.hardware.graphics.common-V3-ndk_vendor',
    'android.hardware.graphics.allocator-V1-ndk':
        lambda lib, partition: 'android.hardware.graphics.allocator-V1-ndk_vendor',
    # the platform's libtensorflowlite_jni is sdk_version current with no vendor
    # variant, so the stock vendor and odm copies each carry their own name
    'libtensorflowlite_jni':
        lambda lib, partition: 'libtensorflowlite_jni_odm'
        if partition == 'odm' else 'libtensorflowlite_jni_vendor',
    # the platform's libvibrator is a system only cc_library, so the stock
    # vendor copy needs a name of its own
    'libvibrator': lambda lib, partition: 'libvibrator_vendor',
    # the platform's libwifi-hal is the generic implementation, and the stock
    # service and autotestwifi open the Unisoc one by soname
    'libwifi-hal': lambda lib, partition: 'libwifi-hal_vendor',
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
