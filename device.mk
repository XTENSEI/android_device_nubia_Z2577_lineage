#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit some common Lineage stuff
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Inherit from the Z2577 vendor blobs
$(call inherit-product, vendor/nubia/Z2577/Z2577-vendor.mk)

# APEX
$(call inherit-product, $(SRC_TARGET_DIR)/product/updatable_apex.mk)

# Virtual A/B with compressed snapshots
PRODUCT_VIRTUAL_AB_COMPRESSION_METHOD := lz4
PRODUCT_VIRTUAL_AB_COMPRESSION_FACTOR := 65536
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/generic_ramdisk.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/vabc_features.mk)

# Boot control
PRODUCT_PACKAGES += \
    android.hardware.boot@1.2-impl \
    android.hardware.boot@1.2-impl.recovery \
    android.hardware.boot@1.2-service

# OTA
PRODUCT_PACKAGES += \
    update_engine \
    update_engine_sideload \
    update_verifier

PRODUCT_PACKAGES += \
    checkpoint_gc \
    otapreopt_script

AB_OTA_POSTINSTALL_CONFIG += \
    RUN_POSTINSTALL_system=true \
    POSTINSTALL_PATH_system=system/bin/otapreopt_script \
    FILESYSTEM_TYPE_system=erofs \
    POSTINSTALL_OPTIONAL_system=true

AB_OTA_POSTINSTALL_CONFIG += \
    RUN_POSTINSTALL_vendor=true \
    POSTINSTALL_PATH_vendor=bin/checkpoint_gc \
    FILESYSTEM_TYPE_vendor=erofs \
    POSTINSTALL_OPTIONAL_vendor=true

# fastbootd
PRODUCT_PACKAGES += \
    android.hardware.fastboot@1.1-impl-mock \
    fastbootd

# Kernel modules, the loader config and the boot mode lists
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/prebuilts/modules/init.insmod.cfg:vendor_dlkm/lib/modules/init.insmod.cfg \
    $(LOCAL_PATH)/prebuilts/modules/modules.load.cali:vendor_dlkm/lib/modules/modules.load.cali \
    $(LOCAL_PATH)/prebuilts/modules/modules.load.charger:vendor_dlkm/lib/modules/modules.load.charger

# Partitions
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# Rootdir, the fstab has to sit in the first stage ramdisk to mount super
PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/rootdir/etc/fstab.ums9230_6h10:$(TARGET_VENDOR_RAMDISK_OUT)/first_stage_ramdisk/fstab.ums9230_6h10
