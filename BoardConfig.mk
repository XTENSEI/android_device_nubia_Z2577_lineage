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

# A/B, virtual A/B with compressed snapshots
AB_OTA_UPDATER := true
AB_OTA_PARTITIONS += \
    boot \
    dtbo \
    init_boot \
    odm \
    product \
    system \
    system_dlkm \
    system_ext \
    vendor \
    vendor_boot \
    vendor_dlkm \
    vbmeta \
    vbmeta_odm \
    vbmeta_product \
    vbmeta_system \
    vbmeta_system_ext \
    vbmeta_vendor
BOARD_USES_METADATA_PARTITION := true

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
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 104857600
BOARD_BOOT_HEADER_VERSION := 4
BOARD_KERNEL_PAGESIZE := 4096
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_FLASH_BLOCK_SIZE := 262144

# Kernel, the stock image ships as a prebuilt
# prebuilts/kernel and prebuilts/dtb.img come out of the stock boot and vendor_boot
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilts/kernel
BOARD_KERNEL_IMAGE_NAME := Image

# Bootloader
TARGET_NO_BOOTLOADER := true

# Recovery, the stock vendor_boot carries the recovery resources
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.ums9230_6h10
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

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
