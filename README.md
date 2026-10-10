# Device tree for the Nubia V80 Max (Z2577)

The nubia V80 Max (codenamed "Z2577") is a budget smartphone from nubia.

## Device specifications

| Basic                   | Spec                                                        |
| ----------------------- | :---------------------------------------------------------- |
| SoC                     | Unisoc T7250 (12 nm)                                        |
| CPU                     | Octa-core (2x 1.8 GHz Cortex-A75 & 6x 1.6 GHz Cortex-A55)   |
| GPU                     | Mali-G57 MP1                                                |
| Memory                  | 8 GB LPDDR4X                                                |
| Shipped Android version | 16                                                          |
| Storage                 | 128/256 GB eMMC 5.1                                         |
| MicroSD                 | microSDXC                                                   |
| Battery                 | Non-removable Li-Polymer 6000 mAh                           |
| Dimensions              | 171.55 x 77.75 x 8.3 mm                                     |
| Display                 | IPS LCD 120 Hz, 6.9 inches, 720 x 1640 pixels               |
| Rear Camera 1           | 50 MP, f/1.8, PDAF                                          |
| Rear Camera 2           | 0.08 MP AI lens                                             |
| Front Camera            | 16 MP                                                       |

## Device Picture

![nubia V80 Max](docs/z2577.jpg)

## Extracting the blobs

`proprietary-files.txt` is the list and the vendor repo is its generated output.
Both need a LineageOS checkout, with this tree at `device/nubia/Z2577` and the
blobs at `vendor/nubia/Z2577`:

    ./extract-files.py
    ./setup-makefiles.py

Soong only accepts letters, digits and `_ . @ + -` in a module name, and
`build/tools/extract-utils` builds one straight from the path, so
`vendor/bin/[` becomes `vendor_bin_[`, which Soong rejects. File names have the
same problem: `lib{bar}.so` would be named `lib{bar}`.
`docs/extract-utils-module-name.patch` covers both, leaving legal names alone.

The patch is lost on every `repo sync`, because `build/tools/extract-utils`
belongs to the LineageOS checkout and not to either repo, so the one symlink it
affects is declared by hand in `Android.bp`. The blob list no longer carries
that entry, so a regeneration never competes with it.
