#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/nubia/Z2577

# Architecture, arm64 only, no 32-bit runtime
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := cortex-a75
TARGET_SUPPORTS_32_BIT_APPS := false
TARGET_SUPPORTS_64_BIT_APPS := true

# Dynamic partitions, values read with lpdump from the stock super.bin
# The build appends the slot suffix, so the names are declared without it
BOARD_SUPER_PARTITION_SIZE := 13690208256
BOARD_SUPER_PARTITION_GROUPS := group_unisoc
BOARD_GROUP_UNISOC_PARTITION_LIST := system system_ext product vendor odm system_dlkm vendor_dlkm
BOARD_GROUP_UNISOC_SIZE := 13686013952

# Boot chain, sizes read off the phone and matched to the backup bins
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_INIT_BOOT_IMAGE_PARTITION_SIZE := 8388608
BOARD_DTBIMAGE_PARTITION_SIZE := 8388608
BOARD_DTBOIMG_PARTITION_SIZE := 8388608

# Platform
TARGET_BOARD_PLATFORM := ums9230

# Display
TARGET_SCREEN_HEIGHT := 1640
TARGET_SCREEN_WIDTH := 720
TARGET_SCREEN_DENSITY := 320

# Properties
TARGET_SYSTEM_PROP += $(DEVICE_PATH)/system.prop
TARGET_VENDOR_PROP += $(DEVICE_PATH)/vendor.prop

# Soong
PRODUCT_SOONG_NAMESPACES += \
    $(DEVICE_PATH)

# TODO(dtb name): the stock dtb lives in vendor_boot.img, the dtb partition is empty
