#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/nubia/Z2577

# The boot artifacts live in the kernel repo, checked out beside the tree
KERNEL_PREBUILT := $(TOP)/kernel/nubia/Z2577/prebuilt

# Architecture, arm64 with the stock 32 bit vendor runtime
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := cortex-a75

# The stock vendor ships 563 32 bit libraries and six 32 bit services, and
# ro.zygote is zygote64_32, so the second arch is built
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv8-a
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_VARIANT_RUNTIME := cortex-a55

TARGET_SUPPORTS_32_BIT_APPS := true
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
    vendor_dlkm
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

# init_boot carries its own header version, Soong does not inherit it from the boot one
BOARD_INIT_BOOT_HEADER_VERSION := 4
BOARD_MKBOOTIMG_INIT_ARGS += --header_version $(BOARD_INIT_BOOT_HEADER_VERSION)
BOARD_FLASH_BLOCK_SIZE := 262144

# GKI, the cmdline and the boot config belong in vendor_boot, boot.img is kernel only
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_KERNEL_CMDLINE := console=ttyS1,115200n8 bootconfig
BOARD_BOOTCONFIG := androidboot.hardware=ums9230_6h10

# The stock vendor ramdisk is lz4 legacy
BOARD_RAMDISK_USE_LZ4 := true

# The stock vendor_boot header addresses, the mkbootimg defaults differ on the ramdisk
BOARD_MKBOOTIMG_ARGS += --base 0x00000000
BOARD_MKBOOTIMG_ARGS += --kernel_offset 0x00008000
BOARD_MKBOOTIMG_ARGS += --ramdisk_offset 0x05400000
BOARD_MKBOOTIMG_ARGS += --tags_offset 0x00000100
BOARD_MKBOOTIMG_ARGS += --dtb_offset 0x01f00000

# Kernel, the stock image ships as a prebuilt
# kernel, dtb.img and dtbo.img come out of the stock boot and vendor_boot
TARGET_PREBUILT_KERNEL := $(KERNEL_PREBUILT)/kernel
TARGET_PREBUILT_DTB := $(KERNEL_PREBUILT)/dtb.img
BOARD_PREBUILT_DTBOIMAGE := $(KERNEL_PREBUILT)/dtbo.img
BOARD_KERNEL_IMAGE_NAME := Image
BOARD_MKBOOTIMG_ARGS += --dtb $(TARGET_PREBUILT_DTB)

# Kernel modules, the stock vendor_dlkm partition ships as a prebuilt
BOARD_VENDOR_KERNEL_MODULES := $(wildcard $(KERNEL_PREBUILT)/modules/*.ko)
BOARD_VENDOR_KERNEL_MODULES_LOAD := $(strip $(shell cat $(KERNEL_PREBUILT)/modules/modules.load))
BOARD_VENDOR_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
TARGET_COPY_OUT_VENDOR_DLKM := vendor_dlkm

# Ramdisk kernel modules, first stage loads these before vendor_dlkm is mounted
BOARD_VENDOR_RAMDISK_KERNEL_MODULES := $(wildcard $(KERNEL_PREBUILT)/modules_ramdisk/*.ko)
BOARD_VENDOR_RAMDISK_KERNEL_MODULES_LOAD := $(strip $(shell cat $(KERNEL_PREBUILT)/modules_ramdisk/modules.load))
BOARD_VENDOR_RAMDISK_RECOVERY_KERNEL_MODULES_LOAD := $(strip $(shell cat $(KERNEL_PREBUILT)/modules_ramdisk/modules.load.recovery))

# System dlkm, the stock GKI modules on their own partition
BOARD_USES_SYSTEM_DLKMIMAGE := true
TARGET_COPY_OUT_SYSTEM_DLKM := system_dlkm
BOARD_SYSTEM_KERNEL_MODULES := $(wildcard $(KERNEL_PREBUILT)/modules_system/*.ko)
BOARD_SYSTEM_KERNEL_MODULES_LOAD := $(strip $(shell cat $(KERNEL_PREBUILT)/modules_system/modules.load))

# ODM image, its own partition, the odm blobs do not belong in the vendor image
BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := erofs
TARGET_COPY_OUT_ODM := odm

# Images, stock carries erofs on every dynamic partition and f2fs on userdata
BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_SYSTEM_EXTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_PRODUCTIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_SYSTEM_DLKMIMAGE_FILE_SYSTEM_TYPE := erofs
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs

# The dynamic partitions are their own images, not subdirectories of system
TARGET_COPY_OUT_VENDOR := vendor
TARGET_COPY_OUT_PRODUCT := product
TARGET_COPY_OUT_SYSTEM_EXT := system_ext

# Bootloader
TARGET_NO_BOOTLOADER := true

# Recovery, the stock vendor_boot carries the recovery resources
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := true
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/rootdir/etc/fstab.ums9230_6h10
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

# Verified boot, the chain and the locations mirror the stock vbmeta
BOARD_AVB_ENABLE := true
BOARD_AVB_ALGORITHM := SHA256_RSA4096
BOARD_AVB_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --set_hashtree_disabled_flag
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 4

BOARD_AVB_BOOT_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_BOOT_ALGORITHM := SHA256_RSA4096
BOARD_AVB_BOOT_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_BOOT_ROLLBACK_INDEX_LOCATION := 1

BOARD_AVB_INIT_BOOT_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_INIT_BOOT_ALGORITHM := SHA256_RSA4096
BOARD_AVB_INIT_BOOT_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_INIT_BOOT_ROLLBACK_INDEX_LOCATION := 8

BOARD_AVB_DTBO_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_DTBO_ALGORITHM := SHA256_RSA4096
BOARD_AVB_DTBO_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_DTBO_ROLLBACK_INDEX_LOCATION := 6

BOARD_AVB_VENDOR_BOOT_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VENDOR_BOOT_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VENDOR_BOOT_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VENDOR_BOOT_ROLLBACK_INDEX_LOCATION := 17

BOARD_AVB_VBMETA_SYSTEM := system system_ext
BOARD_AVB_VBMETA_SYSTEM_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VBMETA_SYSTEM_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_SYSTEM_ROLLBACK_INDEX_LOCATION := 2

BOARD_AVB_VBMETA_SYSTEM_EXT := system_dlkm vendor_dlkm
BOARD_AVB_VBMETA_SYSTEM_EXT_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VBMETA_SYSTEM_EXT_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VBMETA_SYSTEM_EXT_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_SYSTEM_EXT_ROLLBACK_INDEX_LOCATION := 3

BOARD_AVB_VBMETA_VENDOR := vendor
BOARD_AVB_VBMETA_VENDOR_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VBMETA_VENDOR_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VBMETA_VENDOR_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_VENDOR_ROLLBACK_INDEX_LOCATION := 4

BOARD_AVB_VBMETA_PRODUCT := product
BOARD_AVB_VBMETA_PRODUCT_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VBMETA_PRODUCT_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VBMETA_PRODUCT_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_PRODUCT_ROLLBACK_INDEX_LOCATION := 5

BOARD_AVB_VBMETA_ODM := odm
BOARD_AVB_VBMETA_ODM_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_VBMETA_ODM_ALGORITHM := SHA256_RSA4096
BOARD_AVB_VBMETA_ODM_ROLLBACK_INDEX := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)
BOARD_AVB_VBMETA_ODM_ROLLBACK_INDEX_LOCATION := 7

# Platform
TARGET_BOARD_PLATFORM := ums9230
# Not the boot hardware name, the fstab follows androidboot.hardware
TARGET_BOOTLOADER_BOARD_NAME := Z2577
TARGET_OTA_ASSERT_DEVICE := Z2577

# RIL
ENABLE_VENDOR_RIL_SERVICE := true

# Vendor patch level, from the stock ro.vendor.build.security_patch
VENDOR_SECURITY_PATCH := 2026-05-05

# Sepolicy
SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/public
BOARD_VENDOR_SEPOLICY_DIRS += $(DEVICE_PATH)/sepolicy/vendor

# Display
TARGET_SCREEN_HEIGHT := 1640
TARGET_SCREEN_WIDTH := 720
TARGET_SCREEN_DENSITY := 320

# Wi-Fi, the platform hostapd is not built until a driver is set
BOARD_HOSTAPD_DRIVER := NL80211

# Properties
TARGET_SYSTEM_PROP += $(DEVICE_PATH)/system.prop
TARGET_ODM_PROP += $(DEVICE_PATH)/odm.prop
TARGET_VENDOR_PROP += $(DEVICE_PATH)/vendor.prop

# Soong
PRODUCT_SOONG_NAMESPACES += \
    $(DEVICE_PATH)

# VINTF
DEVICE_FRAMEWORK_COMPATIBILITY_MATRIX_FILE := $(DEVICE_PATH)/configs/vintf/framework_compatibility_matrix.xml
ODM_MANIFEST_FILES := $(DEVICE_PATH)/configs/vintf/odm/manifest.xml
ODM_MANIFEST_SKUS += singlesim wifionly
ODM_MANIFEST_SINGLESIM_FILES := $(DEVICE_PATH)/configs/vintf/odm/manifest_singlesim.xml
ODM_MANIFEST_WIFIONLY_FILES := $(DEVICE_PATH)/configs/vintf/odm/manifest_wifionly.xml

# The dtb partition is all zero in the stock backup, so the dtb travels in
# vendor_boot: prebuilt/dtb.img from the kernel repo feeds --dtb
