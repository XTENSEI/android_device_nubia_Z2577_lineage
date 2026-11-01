#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit some common Lineage stuff
$(call inherit-product, vendor/lineage/config/common_full_phone.mk)

# Vendor blobs
$(call inherit-product, vendor/nubia/Z2577/Z2577-vendor.mk)

# APEX
$(call inherit-product, $(SRC_TARGET_DIR)/product/updatable_apex.mk)

# Virtual A/B
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

# Power stats
PRODUCT_PACKAGES += \
    android.hardware.power.stats-service.example

# DRM, health and sensors
PRODUCT_PACKAGES += \
    android.hardware.drm-service.clearkey \
    android.hardware.health-service.example \
    android.hardware.sensors-service.multihal \
    rkp_factory_extraction_tool

# Audio, CAS, composer and OMX
PRODUCT_PACKAGES += \
    android.hardware.audio.service \
    android.hardware.cas@1.2-service \
    android.hardware.graphics.composer@2.4-service \
    android.hardware.media.omx@1.0-service

# KeyMint
PRODUCT_PACKAGES += \
    android.hardware.security.keymint-service \
    android.hardware.hardware_keystore.xml

# Wi-Fi daemons
PRODUCT_PACKAGES += \
    hostapd \
    wpa_supplicant

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

# Kernel modules
PRODUCT_COPY_FILES += \
    kernel/nubia/Z2577/prebuilt/modules/init.insmod.cfg:vendor_dlkm/lib/modules/init.insmod.cfg \
    kernel/nubia/Z2577/prebuilt/modules/modules.load.cali:vendor_dlkm/lib/modules/modules.load.cali \
    kernel/nubia/Z2577/prebuilt/modules/modules.load.charger:vendor_dlkm/lib/modules/modules.load.charger

# Toybox
PRODUCT_PACKAGES += \
    toybox_vendor

# Vendor tools
PRODUCT_PACKAGES += \
    awk_vendor \
    dumpsys_vendor \
    logwrapper_vendor \
    mkshrc_vendor \
    sh_vendor \
    toolbox_vendor

# ODM overlays
PRODUCT_PACKAGES += \
    DualSimOverlay \
    WifiOnlyOverlay \
    WifiOnlySettingsOverlay \
    unisoc_overlay_core_max_cached_processed_28

# VINTF
PRODUCT_PACKAGES += \
    rebootescrow-default.xml_vendor

# Identity
PRODUCT_PACKAGES += \
    android.hardware.identity_credential.xml

# Partitions
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# Rootdir
PRODUCT_PACKAGES += \
    init.environ.rc

PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/rootdir/etc/fstab.ums9230_6h10:$(TARGET_COPY_OUT_VENDOR_RAMDISK)/first_stage_ramdisk/fstab.ums9230_6h10

# Recovery USB
PRODUCT_DEFAULT_PROPERTY_OVERRIDES += \
    ro.recovery.usb.vid=18D1 \
    ro.recovery.usb.adb.pid=D001 \
    ro.recovery.usb.fastboot.pid=4EE0

PRODUCT_COPY_FILES += \
    $(LOCAL_PATH)/rootdir/etc/init.recovery.ums9230_6h10.rc:$(TARGET_COPY_OUT_RECOVERY)/root/init.recovery.ums9230_6h10.rc
