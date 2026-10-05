#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/nubia/Z2577

# Dynamic partitions
BOARD_SUPER_PARTITION_SIZE := 13690208256

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

# Soong
PRODUCT_SOONG_NAMESPACES += \
    $(DEVICE_PATH)

# TODO(dtb name): the stock dtb lives in vendor_boot.img, the dtb partition is empty
