#!/usr/bin/env python3
"""Fail-closed v4 packaging. Never relabel the tracked v3 baseline as v4."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZIP_STORED, ZipFile, ZipInfo
import package_6511_pixel_native_control_v3 as previous

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'native-control/v4-candidate.json'
EXPECTED_PATHS = {
    'driver': 'common/files/aidl/libjamesdsp.so',
    'helper': 'common/files/control/arm64-v8a/jdspctl',
    'app': 'common/files/JamesDSPManagerThePBone.apk',
}
RETIRED_DRIVERS = {
    '266909b6aaf9a81648538369a2671d3f79d47d1f0ea02b56b21cf6cfc1df54ce',
    'cf6e202262dd7925c1245670f3e3e7aa5aacf321fdf8f71ad0378e6e81b33e4a',
}
TRUSTED_APK_SIGNER = 'c18c2d21eee51c357d9485c781be9bf201131c6fa94bab97b93c94b710c40357'

def android_tool(name):
    explicit = os.environ.get('JDSP_' + name.upper()) or shutil.which(name)
    if explicit:
        return explicit
    for key in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        if os.environ.get(key):
            choices = sorted((Path(os.environ[key]) / 'build-tools').glob('*/' + name), reverse=True)
            if choices:
                return str(choices[0])
    raise ValueError('Android SDK verification tool is required: ' + name)

def verify_apk(path):
    cert = subprocess.check_output([android_tool('apksigner'), 'verify', '--print-certs', str(path)], text=True)
    digests = re.findall(r'certificate SHA-256 digest: ([0-9a-fA-F]+)', cert)
    if len(digests) != 1 or digests[0].lower() != TRUSTED_APK_SIGNER:
        raise ValueError('APK does not have the sole authorized signer')
    badging = subprocess.check_output([android_tool('aapt'), 'dump', 'badging', str(path)], text=True)
    match = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
    if not match or match.groups() != ('james.dsp', '62', '1.6.17'):
        raise ValueError('APK package/version is not the v4 beta-4 root integration client')

def candidate(root=ROOT):
    value = json.loads((root / MANIFEST).read_text())
    if value.get('iteration') != 4 or value.get('service') != 'jdsp.control' or value.get('wireProtocol') != 3:
        raise ValueError('Unexpected global-control contract')
    return value

def verify_artifacts(root=ROOT):
    value = candidate(root)
    if value.get('state') != 'ready-for-device-test':
        raise ValueError('V4 native build not imported; refusing to package historical payloads')
    commit = value['nativeSource'].get('commit')
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Missing exact native source commit')
    provenance = json.loads((root / 'native-control/v4-build-provenance.json').read_text())
    if provenance.get('source', {}).get('commit') != commit:
        raise ValueError('Native artifact source/provenance mismatch')
    for kind, expected_path in EXPECTED_PATHS.items():
        artifact = value['artifacts'].get(kind)
        if not artifact or artifact.get('path') != expected_path:
            raise ValueError('Missing or unsafe v4 artifact path: ' + kind)
        data = (root / expected_path).read_bytes()
        digest = sha256(data).hexdigest()
        if digest != artifact.get('sha256') or len(data) != artifact.get('sizeBytes'):
            raise ValueError('V4 hash/size mismatch: ' + kind)
        if kind in ('driver', 'helper'):
            if digest in RETIRED_DRIVERS:
                raise ValueError('Historical native driver cannot be distributed as v4')
            if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
                raise ValueError('V4 native artifacts must be ELF64 AArch64')
            native = provenance.get('artifacts', {}).get(kind, {})
            if native.get('sha256') != digest or not native.get('direct_dt_needed'):
                raise ValueError('Missing matching native ELF/dependency report: ' + kind)
        else:
            if artifact.get('packageId') != 'james.dsp' or artifact.get('versionCode') != 62:
                raise ValueError('Incorrect root integration APK metadata')
            if artifact.get('signatureVerified') is not True or artifact.get('signerSha256') != TRUSTED_APK_SIGNER:
                raise ValueError('APK signer verification must be recorded before packaging')
            verify_apk(root / expected_path)
    if (root / 'common/files/JamesDSPManagerThePBone.apk.meta').read_text() != 'versionCode=62\n':
        raise ValueError('Installer APK version metadata mismatch')
    return value

def build(output, root=ROOT):
    value = verify_artifacts(root)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip()
    if branch not in ('master', 'pixel-test-new-aidl'):
        raise ValueError('V4 distribution requires master or pixel-test-new-aidl')
    props = (root / 'module.prop').read_text()
    if 'version=v6.6-beta-4\n' not in props or 'versionCode=137\n' not in props:
        raise ValueError('Expected the v6.6-beta-4 prerelease metadata')
    payloads = dict(previous.PAYLOADS)
    payloads.pop('native-control/provenance.json', None)
    # This candidate exposes only the ThePBone root app. Retire the prior
    # certificate-inspection path and the classic UI APK from distributable ZIPs.
    for retired in (
        'common/app_migration.sh',
        'common/apk_certificate.sh',
        'common/files/JamesDSPManager.apk',
        'common/files/JamesDSPManager.apk.meta',
    ):
        payloads.pop(retired, None)
    payloads.update({
        'TEMP-ROOT-RELOAD.md': 0o100644,
        'manual-audio-reload.sh': 0o100755,
        'audio-hal-recovery.sh': 0o100755,
        'native-control.sh': 0o100755,
        MANIFEST: 0o100644,
        'native-control/v4-build-provenance.json': 0o100644,
        'native-control/global-service.rule': 0o100644,
        'native-control/default-label-opt-in.rule': 0o100644,
        EXPECTED_PATHS['helper']: 0o100755,
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, mode in payloads.items():
            data = (root / name).read_bytes()
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, data)
    digest = sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n')
    output.with_suffix('.zip.json').write_text(json.dumps(value, indent=2) + '\n')
    return digest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-source', action='store_true')
    args = parser.parse_args()
    value = candidate()
    if args.check_source:
        ready = value.get('state') == 'ready-for-device-test'
        if ready:
            verify_artifacts()
        print('V4 packaging ready=' + str(ready).lower())
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('ready=' + str(ready).lower() + '\n')
        return
    output = ROOT / 'dist/JamesDSPManager-v6.6-beta-4.zip'
    print(build(output))

if __name__ == '__main__':
    main()
