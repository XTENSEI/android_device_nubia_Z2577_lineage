#!/usr/bin/env python3
"""Split the Z2577 history into one logical change per commit.

Rebuilds the branch from the skeleton with every commit carrying a single
concern. Split files are rendered from line ranges of the final blob, so the
end state is byte identical apart from the deliberate tee.te regroup.
"""

import os
import subprocess
import sys

REPO = '/home/andrei/Downloads/Trees/device_nubia_Z2577'
FINAL = '4f3e750'
BASE = '4603bcc'
BRANCH = 'rebuild-z2577'
MSG = '/tmp/z2577_split/message.txt'

LAST = 33


def git(*args, env=None):
    return subprocess.run(
        ['git', *args], cwd=REPO, check=True, text=True,
        capture_output=True, env=env,
    ).stdout


def head_exists():
    return subprocess.run(
        ['git', 'rev-parse', '--verify', '--quiet', 'HEAD'],
        cwd=REPO, capture_output=True,
    ).returncode == 0


def blob(rev, path):
    return git('show', f'{rev}:{path}')


# ranges: (first, last, step), 1 based, tiling the file. alt: step specific lines.

BOARD = {
    'ranges': [
        (1, 7, 1), (8, 15, 10), (16, 16, 10), (17, 37, 11), (38, 38, 11),
        (39, 39, 1), (40, 40, 3), (41, 41, 1), (42, 44, 2), (45, 45, 1),
        (46, 50, 1), (51, 55, 12), (56, 56, 22), (57, 59, 22), (60, 61, 23),
        (62, 62, 22), (63, 63, 23), (64, 64, 12), (65, 66, 12), (67, 67, 13),
        (68, 72, 13), (73, 74, 14), (75, 75, 24), (76, 131, 24), (132, 132, 1),
        (133, 134, 1), (135, 135, 25), (136, 138, 25), (139, 139, 1),
        (140, 142, 1), (143, 143, 7), (144, 144, 8), (145, 146, 8),
        (147, 147, 9), (148, 148, 1), (149, 151, 1), (152, 153, 1),
    ],
    'alt': {
        (39, 39): {1: ['# Dynamic partitions\n']},
        (42, 44): {2: [
            'BOARD_SUPER_PARTITION_GROUPS := group_unisoc_a\n',
            'BOARD_GROUP_UNISOC_A_PARTITION_LIST := system system_ext product vendor odm system_dlkm vendor_dlkm\n',
            'BOARD_GROUP_UNISOC_A_SIZE := 13686013952\n',
        ]},
    },
}

DEVICE = {
    'ranges': [
        (1, 10, 1), (11, 13, 15), (14, 20, 16), (21, 26, 17), (27, 48, 18),
        (49, 53, 19), (54, 56, 20), (57, 60, 21),
    ],
}

CONTEXTS = {
    'ranges': [
        (1, 1, 26), (2, 2, 26), (3, 3, 27), (4, 4, 26), (5, 5, 27),
        (6, 8, 26), (9, 11, 27), (12, 12, 27), (13, 14, 26), (15, 17, 28),
        (18, 20, 29), (21, 23, 30), (24, 26, 31), (27, 31, 32), (32, 34, 33),
    ],
}

FILE_TE = {
    'ranges': [(1, 2, 26), (3, 3, 27), (4, 8, 32), (9, 11, 33)],
}

DEVICE_TE = {
    'ranges': [(1, 2, 26), (3, 5, 27)],
}

TEE_TE = {
    'ranges': [(1, 7, 26), (8, 12, 27)],
    'target': [
        '# TEE\n',
        'allow tee teetz_device:chr_file rw_file_perms;\n',
        'allow tee ss_file:dir create_dir_perms;\n',
        'allow tee ss_file:file create_file_perms;\n',
        '\n',
        '# tsupplicant\n',
        'allow tee vendor_tee_prop:property_service set;\n',
        '\n',
        '# Storage proxy\n',
        'allow tee mmcblk_device:chr_file rw_file_perms;\n',
        'allow tee rpmb_socket:sock_file rw_file_perms;\n',
        'allow tee vendor_storageproxyd_default_prop:property_service set;\n',
    ],
}

PROPERTY_TE = {
    'ranges': [(1, 3, 27), (4, 5, 26)],
}

PROPERTY_CONTEXTS = {
    'ranges': [(1, 3, 27), (4, 5, 26)],
}

MODELS = {
    'BoardConfig.mk': BOARD,
    'device.mk': DEVICE,
    'sepolicy/vendor/device.te': DEVICE_TE,
    'sepolicy/vendor/file.te': FILE_TE,
    'sepolicy/vendor/file_contexts': CONTEXTS,
    'sepolicy/vendor/property.te': PROPERTY_TE,
    'sepolicy/vendor/property_contexts': PROPERTY_CONTEXTS,
    'sepolicy/vendor/tee.te': TEE_TE,
}

# ---------------------------------------------------------------------- steps

STEPS = [
    dict(n=1, date='2026-10-05 21:45:19', subject='Z2577: Initial skeleton tree',
         render=['BoardConfig.mk', 'device.mk'],
         checkout=[(BASE, ['Android.bp', 'AndroidProducts.mk', 'README.md',
                           'docs/z2577.jpg', 'lineage.dependencies',
                           'lineage_Z2577.mk'])]),
    dict(n=2, date='2026-10-05 21:45:19', subject='Z2577: Add super partition groups and sizes',
         render=['BoardConfig.mk']),
    dict(n=3, date='2026-10-05 21:50:00',
         subject='Z2577: BoardConfig: Use group_unisoc as the super partition group',
         body='The super group name loses its slot suffix, which the build appends itself.',
         render=['BoardConfig.mk']),
    dict(n=4, date='2026-10-05 22:59:52', subject='Z2577: Add the vendor blob extraction tooling',
         checkout=[('ac9a13d', ['extract-files.py', 'setup-makefiles.py'])]),
    dict(n=5, date='2026-10-05 23:06:00', subject='Z2577: Add the proprietary blob list',
         checkout=[('ac9a13d', ['proprietary-files.txt'])]),
    dict(n=6, date='2026-10-06 21:21:36',
         subject='proprietary-files: Split the Trusty blobs into their own sections',
         body='Gatekeeper, keymint and the trusty libs shared one security bucket.',
         checkout=[('f6a64fd', ['proprietary-files.txt'])]),
    dict(n=7, date='2026-10-06 21:31:03',
         subject='Z2577: BoardConfig: Use 320 for TARGET_SCREEN_DENSITY',
         body='The stock panel runs at 320 dpi.',
         render=['BoardConfig.mk']),
    dict(n=8, date='2026-10-06 21:32:00', subject='Z2577: Add the stock system properties',
         render=['BoardConfig.mk'], checkout=[('e87ffaa', ['system.prop'])]),
    dict(n=9, date='2026-10-06 21:33:00', subject='Z2577: Add the stock vendor properties',
         body='Drops what the build regenerates and the toggles only MyOS reads.',
         render=['BoardConfig.mk'], checkout=[('e87ffaa', ['vendor.prop'])]),
    dict(n=10, date='2026-10-06 21:37:56',
         subject='BoardConfig: Add the arm64 architecture section',
         body='The device ships arm64-v8a on a Cortex-A75 with no 32-bit runtime.',
         render=['BoardConfig.mk']),
    dict(n=11, date='2026-10-06 21:39:46',
         subject='Z2577: BoardConfig: Enable A/B updates',
         render=['BoardConfig.mk']),
    dict(n=12, date='2026-10-06 21:41:00',
         subject='Z2577: BoardConfig: Configure the boot chain',
         render=['BoardConfig.mk']),
    dict(n=13, date='2026-10-06 21:42:00',
         subject='Z2577: BoardConfig: Build the recovery into vendor_boot',
         render=['BoardConfig.mk']),
    dict(n=14, date='2026-10-06 21:43:00',
         subject='Z2577: BoardConfig: Enable ext4 and f2fs userdata images',
         render=['BoardConfig.mk']),
    dict(n=15, date='2026-10-06 21:44:00', subject='Z2577: Enable updatable APEX',
         render=['device.mk']),
    dict(n=16, date='2026-10-06 21:45:00', subject='Z2577: Configure virtual A/B',
         render=['device.mk']),
    dict(n=17, date='2026-10-06 21:46:00', subject='Z2577: Add the boot control HAL',
         render=['device.mk']),
    dict(n=18, date='2026-10-06 21:47:00', subject='Z2577: Add the OTA packages',
         render=['device.mk']),
    dict(n=19, date='2026-10-06 21:48:00', subject='Z2577: Add fastbootd',
         render=['device.mk']),
    dict(n=20, date='2026-10-06 21:49:00', subject='Z2577: Enable dynamic partitions',
         render=['device.mk']),
    dict(n=21, date='2026-10-06 21:50:00', subject='Z2577: Add the first stage fstab',
         render=['device.mk'], checkout=[('e9d7b5b', ['rootdir/etc/fstab.ums9230_6h10'])]),
    dict(n=22, date='2026-10-06 22:03:58', subject='Z2577: Ship the stock kernel as a prebuilt',
         body='The kernel comes out of the stock boot.img and rebuilds it byte for byte.',
         render=['BoardConfig.mk'], checkout=[('ee7f8c3', ['prebuilts/kernel'])]),
    dict(n=23, date='2026-10-06 22:04:20',
         subject='Z2577: Ship the stock dtb and dtbo as prebuilts',
         render=['BoardConfig.mk'],
         checkout=[('ee7f8c3', ['prebuilts/dtb.img', 'prebuilts/dtbo.img'])]),
    dict(n=24, date='2026-10-06 22:04:40',
         subject='Z2577: Configure verified boot against the stock vbmeta chain',
         body='Chains and rollback locations read from the stock vbmeta_a. Flags 3\n'
              'disables verification so a prebuilt mismatch cannot block bring-up.',
         render=['BoardConfig.mk']),
    dict(n=25, date='2026-10-06 22:43:53',
         subject='Z2577: BoardConfig: Add the sepolicy directories',
         render=['BoardConfig.mk']),
    dict(n=26, date='2026-10-06 22:45:00',
         subject='Z2577: sepolicy: Configure sepolicy for the TEE',
         body='* AOSP already ships tee and tee_exec, the Unisoc device nodes and the\n'
              '  secure storage paths are not',
         render=['sepolicy/vendor/device.te', 'sepolicy/vendor/file.te',
                 'sepolicy/vendor/tee.te', 'sepolicy/vendor/file_contexts',
                 'sepolicy/vendor/property.te', 'sepolicy/vendor/property_contexts']),
    dict(n=27, date='2026-10-06 22:46:00',
         subject='Z2577: sepolicy: Configure sepolicy for the storage proxy',
         body='* The proxies and rpmbserver all run in the tee domain',
         render=['sepolicy/vendor/device.te', 'sepolicy/vendor/file.te',
                 'sepolicy/vendor/tee.te', 'sepolicy/vendor/file_contexts',
                 'sepolicy/vendor/property.te', 'sepolicy/vendor/property_contexts']),
    dict(n=28, date='2026-10-06 22:47:00',
         subject='Z2577: sepolicy: Configure sepolicy for the trusty HAL',
         body='* AOSP ships no trusty HAL domain, this one is new',
         render=['sepolicy/vendor/file_contexts'],
         checkout=[(FINAL, ['sepolicy/public/hal_trustyclientaidl.te',
                            'sepolicy/vendor/hal_trustyclientaidl_default.te',
                            'sepolicy/vendor/service_contexts'])]),
    dict(n=29, date='2026-10-06 22:48:00',
         subject='Z2577: sepolicy: Configure sepolicy for the gatekeeper HAL',
         body='* AOSP already declares the domain, only the tee device is granted',
         render=['sepolicy/vendor/file_contexts'],
         checkout=[(FINAL, ['sepolicy/vendor/hal_gatekeeper_default.te'])]),
    dict(n=30, date='2026-10-06 22:49:00',
         subject='Z2577: sepolicy: Configure sepolicy for the keymint HAL',
         body='* The Unisoc service keeps its own domain on top of hal_keymint',
         render=['sepolicy/vendor/file_contexts'],
         checkout=[(FINAL, ['sepolicy/vendor/hal_keymint_unisoc.te'])]),
    dict(n=31, date='2026-10-06 22:50:00',
         subject='Z2577: sepolicy: Configure sepolicy for the identity HAL',
         body='* AOSP already declares the domain, only the tee device is granted',
         render=['sepolicy/vendor/file_contexts'],
         checkout=[(FINAL, ['sepolicy/vendor/hal_identity_default.te'])]),
    dict(n=32, date='2026-10-06 22:51:00',
         subject='Z2577: sepolicy: Configure sepolicy for the sensors',
         body='* The stock sensors service already runs as hal_sensors_default, only the\n'
              '  ZTE paths are added',
         render=['sepolicy/vendor/file.te', 'sepolicy/vendor/file_contexts']),
    dict(n=33, date='2026-10-06 22:52:00',
         subject='Z2577: sepolicy: Configure sepolicy for the touch',
         body='* The stock tree ships no touch HAL, the label covers the panel data',
         render=['sepolicy/vendor/file.te', 'sepolicy/vendor/file_contexts']),
]


# ------------------------------------------------------------------ rendering

def load_models():
    for path, model in MODELS.items():
        lines = blob(FINAL, path).splitlines(keepends=True)
        if 'target' in model:
            model['lines'] = model['target']
        else:
            model['lines'] = lines
        model['path'] = path
        check_ranges(model)


def check_ranges(model):
    lines = model['lines']
    pos = 1
    for first, last, _step in model['ranges']:
        assert first == pos, f"{model['path']}: gap before line {first}"
        assert last >= first, f"{model['path']}: empty range {first}-{last}"
        pos = last + 1
    assert pos == len(lines) + 1, (
        f"{model['path']}: ranges cover {pos - 1} lines, file has {len(lines)}")
    for (first, last), alts in model.get('alt', {}).items():
        for step, replacement in alts.items():
            assert step < LAST, f"{model['path']}: alt at final step"
            assert first in [r[0] for r in model['ranges']]


def render(model, step):
    out = []
    for first, last, owner in model['ranges']:
        if owner > step:
            continue
        alt = model.get('alt', {}).get((first, last), {}).get(step)
        out.extend(alt if alt is not None else model['lines'][first - 1:last])
    return out


def render_all(step):
    return {path: render(model, step) for path, model in MODELS.items()}


def coverage():
    tracked = git('ls-tree', '-r', '--name-only', FINAL).split()
    planned = []
    for step in STEPS:
        planned.extend(step.get('render', []))
        for _rev, paths in step.get('checkout', []):
            planned.extend(paths)
    counts = {}
    for path in planned:
        counts[path] = counts.get(path, 0) + 1
    missing = sorted(set(tracked) - set(planned))
    extra = sorted(set(planned) - set(tracked))
    assert not missing, f'not covered by any step: {missing}'
    assert not extra, f'planned but not in the final tree: {extra}'
    return len(tracked), len(planned)


# ------------------------------------------------------------------- plumbing

def write_file(path, lines):
    full = os.path.join(REPO, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as fh:
        fh.writelines(lines)


def commit(step):
    body = step.get('body')
    text = step['subject'] + '\n'
    if body:
        text += '\n' + body + '\n'
    with open(MSG, 'w') as fh:
        fh.write(text)
    env = dict(os.environ,
               GIT_AUTHOR_DATE=step['date'] + ' +0800',
               GIT_COMMITTER_DATE=step['date'] + ' +0800')
    git('commit', '-S', '-s', '-F', MSG, env=env)


def dry_run():
    load_models()
    tracked, planned = coverage()
    print(f'files: {tracked} tracked, {planned} planned')

    for step in STEPS:
        paths = list(step.get('render', []))
        for _rev, files in step.get('checkout', []):
            paths.extend(files)
        assert paths, f"step {step['n']} touches nothing"
        print(f"{step['n']:2d} {step['date']} {step['subject']}")

    print('\n--- BoardConfig.mk at step 1 ---')
    print(''.join(render(MODELS['BoardConfig.mk'], 1)), end='')
    print('--- BoardConfig.mk at step 3 ---')
    print(''.join(render(MODELS['BoardConfig.mk'], 3)), end='')
    print('--- file_contexts at step 26 ---')
    print(''.join(render(MODELS['sepolicy/vendor/file_contexts'], 26)), end='')
    print('--- file_contexts at step 27 ---')
    print(''.join(render(MODELS['sepolicy/vendor/file_contexts'], 27)), end='')

    print('--- tee.te at the TEE step ---')
    print(''.join(render(MODELS['sepolicy/vendor/tee.te'], 26)), end='')
    print('--- tee.te at the storage step ---')
    print(''.join(render(MODELS['sepolicy/vendor/tee.te'], 27)), end='')
    print('--- file.te at the touch step ---')
    print(''.join(render(MODELS['sepolicy/vendor/file.te'], 33)), end='')


def run():
    load_models()
    coverage()
    assert not git('status', '--porcelain').strip(), 'working tree is dirty'

    git('checkout', '--orphan', BRANCH)
    git('rm', '-r', '--cached', '.')

    for step in STEPS:
        for rev, paths in step.get('checkout', []):
            git('checkout', rev, '--', *paths)
        for path in step.get('render', []):
            write_file(path, render(MODELS[path], step['n']))
            git('add', path)

        staged = git('diff', '--cached', '--name-only').split()
        assert staged, f"step {step['n']}: nothing staged"
        before = git('rev-parse', 'HEAD').strip() if head_exists() else None
        commit(step)
        if before:
            stat = git('diff', '--stat', before, 'HEAD', '--').strip()
        else:
            stat = git('show', '--stat', '--format=', 'HEAD').strip()
        print(f"\n=== {git('log', '-1', '--format=%h %s')}")
        print(stat)

    print('\n=== tree check against the old tip')
    diff = git('diff', '--stat', FINAL, 'HEAD', '--')
    print(diff if diff.strip() else '(identical)')


if __name__ == '__main__':
    if '--dry' in sys.argv:
        dry_run()
    else:
        run()
