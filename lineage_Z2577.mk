#
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from the device configuration
$(call inherit-product, $(LOCAL_PATH)/device.mk)

## Device identifier, this must come after all inclusions
PRODUCT_BRAND := nubia
PRODUCT_DEVICE := Z2577
PRODUCT_MANUFACTURER := nubia
PRODUCT_MODEL := V80 Max
PRODUCT_NAME := lineage_Z2577

PRODUCT_SYSTEM_DEFAULT_LANGUAGE := en-US
PRODUCT_SYSTEM_DEFAULT_COUNTRY := US

PRODUCT_GMS_CLIENTID_BASE := android-nubia-Z2577

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRIVATE_BUILD_DESC="P615F02-user 16 BP2A.250605.031.A3 20260522.092043 release-keys" \
    BuildFingerprint=nubia/P615F02/P615F02:16/BP2A.250605.031.A3/20260522.092043:user/release-keys
