#!/usr/bin/env python3
"""Package only independently inspected embedded-v5 artifacts; never relabel v4."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import package_native_control_v4 as baseline
from native_v5 import validate_v5_elf as gate

ROOT = baseline.ROOT
MANIFEST = 'native-control/v5-candidate.json'
PROVENANCE = 'native-control/v5-build-provenance.json'
NOTICES = 'native-control/v5-NOTICES.txt'
EXPECTED_PATHS = baseline.EXPECTED_PATHS
VERSION = 'v6.6-beta-5.3'
VERSION_CODE = 143
PROFILE = json.loads(gate.PROFILE.read_text())


def readelf_tool():
    tool = os.environ.get('JDSP_READELF') or shutil.which('llvm-readelf') or shutil.which('readelf')
    if not tool:
        raise ValueError('Set JDSP_READELF to a trusted LLVM readelf executable')
    return tool


def candidate(root=ROOT):
    value = json.loads((root / MANIFEST).read_text())
    if (value.get('iteration') != 5 or value.get('wireProtocol') != 3 or
            value.get('service') != 'jdsp.control' or
            value.get('descriptor') != 'lightning.dsp.IJamesDspControl' or
            value.get('profile') != PROFILE['profile']):
        raise ValueError('Unexpected embedded v5 contract/profile')
    return value


def verify_artifacts(root=ROOT, readelf=None):
    value = candidate(root)
    if value.get('state') != 'ready-for-device-test':
        raise ValueError('V5 native build not imported; refusing historical payloads')
    commit = value.get('nativeSource', {}).get('commit', '')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Missing exact v5 source commit')
    report = json.loads((root / PROVENANCE).read_text())
    if (report.get('iteration') != 5 or report.get('controlProtocol') != 3 or
            report.get('profile') != PROFILE['profile'] or
            report.get('state') != 'elf-validated-runtime-unverified' or
            report.get('source', {}).get('commit') != commit):
        raise ValueError('V5 source/provenance mismatch')
    evidence = report.get('embeddedCodeEvidence', {})
    for digest in (report.get('source', {}).get('aospManifestSha256'),
                   evidence.get('unstrippedSha256'), evidence.get('loadSegmentsSha256')):
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Missing hash-bound embedded code evidence')
    if evidence.get('definedSymbolsVerified') is not True:
        raise ValueError('Missing embedded implementation evidence')
    notices = value.get('notices', {})
    if notices.get('path') != NOTICES:
        raise ValueError('Missing v5 redistribution notices')
    text = (root / NOTICES).read_bytes()
    if not text.strip() or notices.get('sha256') != sha256(text).hexdigest() or notices.get('sizeBytes') != len(text):
        raise ValueError('V5 redistribution notices hash/size mismatch')
    readelf = readelf or readelf_tool()
    for kind, name in EXPECTED_PATHS.items():
        artifact = value.get('artifacts', {}).get(kind, {})
        if artifact.get('path') != name:
            raise ValueError('Missing or unsafe v5 payload path: ' + kind)
        path = root / name
        data = path.read_bytes()
        digest = sha256(data).hexdigest()
        if artifact.get('sha256') != digest or artifact.get('sizeBytes') != len(data):
            raise ValueError('V5 hash/size mismatch: ' + kind)
        if kind == 'app':
            if (artifact.get('packageId') != 'james.dsp' or artifact.get('versionCode') != 62 or
                    artifact.get('versionName') != '1.6.17' or artifact.get('signatureVerified') is not True or
                    artifact.get('signerSha256') != baseline.TRUSTED_APK_SIGNER):
                raise ValueError('Incorrect signed root app metadata')
            baseline.verify_apk(path)
            continue
        if digest in baseline.RETIRED_DRIVERS:
            raise ValueError('Retired driver cannot be v5')
        fingerprint = gate.load_fingerprint(data)
        if kind == 'driver' and fingerprint != evidence['loadSegmentsSha256']:
            raise ValueError('Driver load segments differ from embedding evidence')
        dynamic = subprocess.check_output([readelf, '--dynamic', '--wide', str(path)], text=True)
        symbols = subprocess.check_output([readelf, '--dyn-syms', '--wide', str(path)], text=True)
        actual = gate.verify_dynamic(dynamic, symbols, PROFILE[kind + 'AllowedNeeded'], kind == 'driver')
        expected = report.get('artifacts', {}).get(kind, {})
        if expected.get('sha256') != digest or expected.get('sizeBytes') != len(data):
            raise ValueError('V5 artifact/provenance hash mismatch: ' + kind)
        for key in ('direct_dt_needed', 'soname', 'nodelete'):
            if actual[key] != expected.get(key):
                raise ValueError('V5 actual ELF/provenance mismatch: ' + kind + '/' + key)
    if (root / 'common/files/JamesDSPManagerThePBone.apk.meta').read_text() != 'versionCode=62\n':
        raise ValueError('Installer APK version metadata mismatch')
    return value


def distribution_version(root=ROOT):
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip()
    if branch not in ('pixel-test-new-aidl', 'samsung-test-new-aidl'):
        raise ValueError('V5 distribution requires pixel-test-new-aidl or samsung-test-new-aidl')
    props = (root / 'module.prop').read_text()
    if f'version={VERSION}\n' not in props or f'versionCode={VERSION_CODE}\n' not in props:
        raise ValueError('Expected embedded v5 module version metadata')
    return VERSION


def payloads():
    result = dict(baseline.previous.PAYLOADS)
    for name in ('native-control/provenance.json', 'common/app_migration.sh',
                 'common/apk_certificate.sh', 'common/files/JamesDSPManager.apk',
                 'common/files/JamesDSPManager.apk.meta', 'update.json'):
        result.pop(name, None)
    # This experiment contains one genuine ARM64 AIDL build, not historical
    # legacy binaries presented as another v5 implementation.
    for name in tuple(result):
        if name.endswith('/libjamesdsp.so') and name != EXPECTED_PATHS['driver']:
            result.pop(name)
    result.update({
        'TEMP-ROOT-RELOAD.md': 0o100644, 'SAMSUNG-RECOVERY.md': 0o100644,
        'EMBEDDED-CONTROL-V5.md': 0o100644,
        'audio-hal-recovery.sh': 0o100755, 'aidl-audio-recovery.sh': 0o100755,
        'aidl-effect-mount.sh': 0o100755, 'native-control.sh': 0o100755,
        MANIFEST: 0o100644, PROVENANCE: 0o100644, NOTICES: 0o100644,
        'native-control/global-service.rule': 0o100644,
        'native-control/default-label-opt-in.rule': 0o100644,
        EXPECTED_PATHS['helper']: 0o100755,
    })
    return result


def build(output, root=ROOT):
    value = verify_artifacts(root)
    distribution_version(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, mode in payloads().items():
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, (root / name).read_bytes())
    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n')
    output.with_suffix('.zip.json').write_text(json.dumps(value, indent=2) + '\n')
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-source', action='store_true')
    args = parser.parse_args()
    if args.check_source:
        ready = candidate().get('state') == 'ready-for-device-test'
        if ready:
            verify_artifacts()
        print('V5 packaging ready=' + str(ready).lower())
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('ready=' + str(ready).lower() + '\n')
        return
    print(build(ROOT / ('dist/JamesDSPManager-' + distribution_version() + '.zip')))


if __name__ == '__main__':
    main()
