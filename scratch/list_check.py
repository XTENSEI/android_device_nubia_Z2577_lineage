#!/usr/bin/env python3
"""Parse proprietary-files.txt with extract-utils and report what it sees."""

import sys
from collections import Counter

sys.path.insert(0, '/home/andrei/romtools/WORK/rom/refs/android_tools_extract-utils')

from extract_utils.file import FileList

LIST = '/home/andrei/Downloads/Trees/device_nubia_Z2577/proprietary-files.txt'


def main():
    fl = FileList(check_elf=True)
    fl.add_from_file(LIST)

    files = list(fl.files)
    partitions = Counter(f.partition for f in files)
    args = Counter()
    for f in files:
        for arg in f.args or {}:
            args[str(arg)] += 1

    print(f'{len(files)} files, {len(fl.partitions)} partitions')
    for name, count in sorted(partitions.items()):
        print(f'  {name}: {count}')
    print(f'{len(list(fl.package_symlinks))} symlink entries, '
          f'{len(list(fl.pinned_files))} pinned')
    print('args: ' + (', '.join(f'{k} x{v}' for k, v in args.items()) or 'none'))

    # Module names have to be unique across the generated Android.bp.
    names = Counter()
    for f in files:
        names[f.basename] += 1
    dupes = {n: c for n, c in names.items() if c > 1}
    print(f'\nduplicate basenames: {len(dupes)}')
    for name, count in sorted(dupes.items())[:10]:
        print(f'  {name} x{count}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
