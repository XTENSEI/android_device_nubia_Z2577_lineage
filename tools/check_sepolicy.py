#!/usr/bin/env python3
# SPDX-FileCopyrightText: The Z2577 Project
# SPDX-License-Identifier: Apache-2.0
#
# Compile the device sepolicy with checkpolicy, the way the build does.
# Names the corpus does not declare are stubbed, files it rejects are dropped
# and reported. Contexts files and neverallow are out of scope.
#

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POLICY_VERSION = '30'

# system/sepolicy files that precede the .te files, in Soong's order
SKELETON = (
    'flagging/flagging_macros',
    'private/security_classes',
    'private/initial_sids',
    'private/access_vectors',
    'public/global_macros',
    'public/neverallow_macros',
    'private/mls_macros',
    'private/mls_decl',
    'private/mls',
    'private/policy_capabilities',
    'public/te_macros',
    'public/ioctl_defines',
    'public/ioctl_macros',
    'public/nlmsg_defines',
    'public/nlmsg_macros',
    'public/attributes',
    'private/attributes',
)

TAIL = (
    'private/roles_decl',
    'public/roles',
    'private/users',
    'private/initial_sid_contexts',
    'private/fs_use',
    'private/genfs_contexts',
    'private/port_contexts',
)

# The flags the build passes to m4. They decide which rules a macro expands to,
# not whether the result parses, but m4 evaluates an undefined one and fails.
M4_DEFS = {
    'mls_num_sens': '1',
    'mls_num_cats': '1024',
    'target_arch': 'arm64',
    'target_build_variant': 'userdebug',
    'target_full_treble': 'true',
    'target_with_asan': 'false',
    'target_with_dexpreopt': 'false',
    'target_with_native_coverage': 'false',
    'target_exclude_build_test': 'false',
    'target_recovery': 'false',
}

DIAG = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<kind>ERROR|WARNING) '(?P<msg>[^']*)'")
UNKNOWN_TYPE = re.compile(r'unknown type (?P<name>\S+)')
UNKNOWN_ATTR = re.compile(r'attribute (?P<name>\S+) is not declared')


def device_dirs():
    """Every directory under sepolicy/ that holds .te files."""
    return sorted(
        path for path in (REPO / 'sepolicy').iterdir()
        if path.is_dir() and list(path.glob('*.te'))
    )


def te_files(directory):
    return sorted(directory.glob('*.te'))


def platform_te(platform):
    files = []
    for sub in ('public', 'private', 'vendor'):
        files += sorted((platform / sub).glob('*.te'))
    return files


def build_conf(platform, ours, stubs, skip, m4, board_api_level, output):
    """One m4 pass over the policy, in the build's own order."""
    inputs = [platform / name for name in SKELETON if (platform / name).exists()]
    if stubs:
        handle, name = tempfile.mkstemp(suffix='.te', prefix='stubs-')
        with os.fdopen(handle, 'w') as stub:
            stub.write('\n'.join(stubs) + '\n')
        inputs.append(Path(name))
    inputs += platform_te(platform)
    for directory in ours:
        inputs += te_files(directory)
    inputs += [platform / name for name in TAIL if (platform / name).exists()]
    inputs = [path for path in inputs if str(path) not in skip]

    command = [str(m4), '-s', '--fatal-warnings']
    for key, value in list(M4_DEFS.items()) + [('target_board_api_level', str(board_api_level))]:
        command.append(f'-D{key}={value}')
    command += [str(path) for path in inputs]

    with open(output, 'w') as conf:
        return subprocess.run(command, stdout=conf, stderr=subprocess.PIPE, text=True)


def compile_conf(checkpolicy, conf):
    return subprocess.run(
        [str(checkpolicy), '-M', '-c', POLICY_VERSION, '-o', '/dev/null', str(conf)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    ).stdout


def first_error(text):
    for line in text.splitlines():
        match = DIAG.match(line)
        if match and match.group('kind') == 'ERROR':
            return match
    return None


def stub_for(message):
    """A declaration that satisfies an unresolved name, where one can."""
    for pattern, keyword in ((UNKNOWN_TYPE, 'type'), (UNKNOWN_ATTR, 'attribute')):
        match = pattern.search(message)
        if match:
            return f'{keyword} {match.group("name")};'
    return None


def build_top():
    """The AOSP tree this device tree is checked out in, if any."""
    top = os.environ.get('ANDROID_BUILD_TOP')
    if top:
        return Path(top)
    top = REPO.parents[2]
    return top if (top / 'system' / 'sepolicy' / 'private' / 'security_classes').exists() else None


def dropped_declares(message, dropped):
    """True when a platform file left out of the corpus spells this name."""
    for pattern in (UNKNOWN_TYPE, UNKNOWN_ATTR):
        match = pattern.search(message)
        if match:
            return any(match.group('name') in Path(path).read_text(errors='ignore')
                       for path in dropped)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-sepolicy', help='path to system/sepolicy sources')
    parser.add_argument('--checkpolicy', help='checkpolicy binary')
    parser.add_argument('--m4', help='m4 binary')
    parser.add_argument('--board-api-level', type=int, default=36)
    parser.add_argument('--max-rounds', type=int, default=120)
    parser.add_argument('--keep-conf', help='write the generated conf here')
    args = parser.parse_args()

    top = build_top()
    # In a tree, the build's own checkpolicy is the one that compiles it.
    platform = args.system_sepolicy or os.environ.get('SYSTEM_SEPOLICY')
    if not platform and top:
        platform = top / 'system' / 'sepolicy'
    platform = Path(platform) if platform else None
    if not platform or not (platform / 'private' / 'security_classes').exists():
        sys.exit('no system/sepolicy sources: run inside the tree, or pass --system-sepolicy')

    m4 = args.m4 or (top and str(top / 'prebuilts' / 'build-tools' / 'linux-x86' / 'bin' / 'm4'))
    m4 = m4 if m4 and Path(m4).exists() else shutil.which('m4')
    checkpolicy = args.checkpolicy
    if not checkpolicy and top:
        built = top / 'out' / 'host' / 'linux-x86' / 'bin' / 'checkpolicy'
        checkpolicy = str(built) if built.exists() else None
    checkpolicy = checkpolicy if checkpolicy and Path(checkpolicy).exists() else shutil.which('checkpolicy')
    if not m4 or not checkpolicy:
        sys.exit('m4 and checkpolicy have to be on the path')

    ours = device_dirs()
    if not ours:
        sys.exit('no .te files under sepolicy/')
    mine = {str(path) for directory in ours for path in te_files(directory)}
    conf = Path(args.keep_conf) if args.keep_conf else Path(
        tempfile.mkstemp(prefix='vendor_sepolicy.', suffix='.conf')[1])

    stubs, skip, findings = [], [], []
    stuck, last = None, None
    exhausted = False
    m4_error = ''
    for _ in range(args.max_rounds):
        result = build_conf(platform, ours, stubs, skip, m4, args.board_api_level, conf)
        if result.returncode:
            m4_error = result.stderr.strip()
            break
        error = first_error(compile_conf(checkpolicy, conf))
        if not error:
            break
        key = (error.group('file'), error.group('line'), error.group('msg'))
        last = key
        if error.group('file') in mine and key not in findings:
            findings.append(key)
        stub = stub_for(error.group('msg'))
        if stub and stub not in stubs:
            stubs.append(stub)
            continue
        if error.group('file') not in mine and error.group('file') not in skip:
            skip.append(error.group('file'))
            continue
        stuck = key
        break
    else:
        exhausted = True
        if last and last not in findings:
            findings.append(last)

    print(f'platform policy: {platform}')
    print(f'device policy:   {len(ours)} dirs, {len(mine)} .te files')
    if stubs:
        print(f'names this corpus does not declare, stubbed: {len(stubs)}')
        for stub in stubs:
            print(f'  {stub}')
    if skip:
        print(f'platform files this checkpolicy rejects with -c {POLICY_VERSION}, '
              f'dropped from the corpus: {len(skip)}')
        for name in skip:
            print(f'  {name}')
    if m4_error:
        print(f'\nm4 failed:\n{m4_error}')
        return 1
    if stuck and stuck not in findings:
        findings.append(stuck)
    if exhausted:
        print(f'\nstopped after {args.max_rounds} rounds, so the last error still stands:')
    # A name a dropped platform file declares is a gap in the corpus, not a
    # finding: dropping a file takes its declarations with it.
    errors = [f for f in findings if not dropped_declares(f[2], skip)]
    gaps = [f for f in findings if dropped_declares(f[2], skip)]
    if gaps:
        print(f'\nnot checked here, a dropped platform file declares these: {len(gaps)}')
        for path, line, message in gaps:
            print(f'  {path}:{line}: {message}')
    if errors:
        print('\nsepolicy errors:')
        for path, line, message in errors:
            print(f'  {path}:{line}: {message}')
        return 1
    if exhausted:
        return 1
    if not args.keep_conf:
        conf.unlink()
    print('\nclean: m4 and checkpolicy over the .te files. Contexts files and the '
          'partition neverallow masks belong to the build, not to this check.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
