#!/usr/bin/env python3
"""Fail-closed package of the LightningDSP module."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import package_6511_pixel_native_control_v3 as baseline
from ldsp import validate_ldsp_elf as elf_gate

VERSION = 'v6.7.1-beta-1'
VERSION_CODE = 162
APP_PACKAGE = 'com.lightning.dsp'
APP_VERSION = '1.7.1-beta-1'
APP_CODE = 81
APP_SOURCE_COMMIT = '4535caad0db1332c7fe2680a0d3cb464545467da'
TRUSTED_APK_SIGNER = 'c18c2d21eee51c357d9485c781be9bf201131c6fa94bab97b93c94b710c40357'
CANDIDATE = 'native-control/ldsp-candidate.json'
PROVENANCE = 'native-control/ldsp-build-provenance.json'
NOTICES = 'native-control/ldsp-NOTICES.txt'
DRIVER = 'common/files/dual-entry-arm64/lightningdsplib.so'
HELPER = 'common/files/control/arm64-v8a/ldspctl'
APP = 'common/files/LightningDSP.apk'


def android_tool(name):
    explicit = os.environ.get('LDSP_' + name.upper()) or shutil.which(name)
    if explicit:
        return explicit
    for key in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'):
        if os.environ.get(key):
            candidates = sorted((Path(os.environ[key]) / 'build-tools').glob('*/' + name), reverse=True)
            if candidates:
                return str(candidates[0])
    raise ValueError('Android SDK verification tool required: ' + name)


def readelf_tool():
    tool = os.environ.get('LDSP_READELF') or shutil.which('llvm-readelf')
    if not tool:
        raise ValueError('Set LDSP_READELF to a trusted LLVM readelf executable')
    return tool


def verify_apk(path):
    signer = subprocess.check_output(
        [android_tool('apksigner'), 'verify', '--print-certs', str(path)], text=True)
    digests = re.findall(r'certificate SHA-256 digest: ([0-9a-fA-F]+)', signer)
    if len(digests) != 1 or digests[0].lower() != TRUSTED_APK_SIGNER:
        raise ValueError('APK is not signed solely with the authorized owner key')
    badging = subprocess.check_output([android_tool('aapt'), 'dump', 'badging', str(path)], text=True)
    match = re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging)
    if not match or match.groups() != (APP_PACKAGE, str(APP_CODE), APP_VERSION):
        raise ValueError('APK package/version mismatch')
    # This module now sends a private startup command. Do not ship it with the
    # previous signed APK, which has no handler for that action.
    startup_action = b'com.lightning.dsp.root.service.START_BACKGROUND'
    with ZipFile(path) as archive:
        supports_startup = any(
            startup_action in archive.read(name)
            for name in archive.namelist()
            if re.fullmatch(r'classes[0-9]*\.dex', name))
    if not supports_startup:
        raise ValueError('Root APK lacks background startup support; integrate the new signed app before packaging')



def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def verify_candidate(root=ROOT, readelf=None):
    manifest = json.loads((root / CANDIDATE).read_text())
    provenance = json.loads((root / PROVENANCE).read_text())
    if (manifest.get('iteration') != 6 or manifest.get('state') != 'ready-for-package' or
            manifest.get('wireProtocol') != 3 or manifest.get('service') != 'ldsp.control' or
            manifest.get('descriptor') != 'lightning.dsp.ILightningDspControl' or
            manifest.get('profile') != 'dual-entry-effect-v4-legacy-arm64'):
        raise ValueError('Unexpected LightningDSP service/profile contract')
    source = manifest.get('nativeSource', {})
    if (source.get('branch') != 'ldsp-rebrand' or
            source.get('commit') != '4971a4d6619c22c40ca341c659bd579eb1d8f06a' or
            provenance.get('source', {}).get('commit') != source.get('commit')):
        raise ValueError('Native source/provenance pin mismatch')
    app_source = manifest.get('appSource', {})
    app_artifact = manifest.get('artifacts', {}).get('app', {})
    if (app_source.get('commit') != APP_SOURCE_COMMIT or
            app_source.get('buildBaseCommit') != APP_SOURCE_COMMIT or
            app_source.get('builtFromWorkingTree') is not False or
            app_artifact.get('sourceCommit') != APP_SOURCE_COMMIT or
            app_source.get('buildNote') != 'Signed root APK built from the committed app source at appSource.commit.'):
        raise ValueError('Signed app source/provenance pin mismatch')
    if provenance.get('state') != 'elf-validated-runtime-unverified':
        raise ValueError('Native artifact has not passed static ELF validation')
    notice = manifest.get('notices', {})
    notice_path = root / NOTICES
    if (notice.get('path') != NOTICES or not notice_path.is_file() or
            notice.get('sha256') != digest(notice_path) or notice.get('sizeBytes') != notice_path.stat().st_size):
        raise ValueError('Native redistribution notices hash mismatch')
    expected = {'app': APP, 'driver': DRIVER, 'helper': HELPER}
    readelf = readelf or readelf_tool()
    for kind, path_name in expected.items():
        item = manifest.get('artifacts', {}).get(kind, {})
        path = root / path_name
        if item.get('path') != path_name or not path.is_file():
            raise ValueError('Missing or wrong payload path: ' + kind)
        if item.get('sha256') != digest(path) or item.get('sizeBytes') != path.stat().st_size:
            raise ValueError('Payload hash/size mismatch: ' + kind)
        if kind == 'app':
            if (item.get('packageId') != APP_PACKAGE or item.get('versionName') != APP_VERSION or
                    item.get('versionCode') != APP_CODE or item.get('signatureVerified') is not True or
                    item.get('signerSha256') != TRUSTED_APK_SIGNER):
                raise ValueError('Signed APK metadata is not the authorized rebrand build')
            verify_apk(path)
        else:
            artifact = provenance.get('artifacts', {}).get(kind, {})
            if artifact.get('sha256') != item.get('sha256') or artifact.get('sizeBytes') != item.get('sizeBytes'):
                raise ValueError('Native bundle/provenance mismatch: ' + kind)
    profile = json.loads((ROOT / 'tools/ldsp/ldsp-profile.json').read_text())
    for kind, path_name in (('driver', DRIVER), ('helper', HELPER)):
        path = root / path_name
        dynamic = subprocess.check_output([readelf, '--dynamic', '--wide', str(path)], text=True)
        symbols = subprocess.check_output([readelf, '--dyn-syms', '--wide', str(path)], text=True)
        actual = elf_gate.verify_dynamic(dynamic, symbols, profile[kind + 'AllowedNeeded'], kind == 'driver')
        artifact = provenance['artifacts'][kind]
        if (actual['direct_dt_needed'] != artifact.get('direct_dt_needed') or
                actual['soname'] != artifact.get('soname') or
                actual['nodelete'] != (kind == 'driver')):
            raise ValueError('Actual ELF dynamic tags differ from the validated native report: ' + kind)
        fingerprint = elf_gate.load_fingerprint(path.read_bytes())
        if kind == 'driver' and fingerprint != provenance.get('elfEvidence', {}).get('embeddedCodeEvidence', {}).get('loadSegmentsSha256'):
            raise ValueError('Driver load segments differ from inspected embedded-code evidence')
    if (root / 'common/files/LightningDSP.apk.meta').read_text() != f'versionCode={APP_CODE}\n':
        raise ValueError('Module APK metadata sidecar mismatch')
    props = (root / 'module.prop').read_text()
    if (f'version={VERSION}\n' not in props or f'versionCode={VERSION_CODE}\n' not in props or
            'id=ainur_lightningdsp\n' not in props):
        raise ValueError('Module identity/version metadata mismatch')
    return manifest


def payloads():
    modes = dict(baseline.PAYLOADS)
    result = {}
    rename = {
        'jdsp_app.sh': 'lightningdsp_app.sh',
        'jdsp_app_handle.sh': 'lightningdsp_app_handle.sh',
        'common/files/JamesDSPManagerThePBone.apk': APP,
        'common/files/JamesDSPManagerThePBone.apk.meta': 'common/files/LightningDSP.apk.meta',
    }
    excluded = {'JDSP_banner.png', 'common/app_migration.sh', 'update.json', 'NATIVE-CONTROL.md', 'native-control/provenance.json',
                'native-control/v4-candidate.json', 'native-control/v5-candidate.json',
                'native-control/v5-build-provenance.json', 'native-control/v5-NOTICES.txt',
                'common/files/JamesDSPManager.apk', 'common/files/JamesDSPManager.apk.meta'}
    for old, mode in modes.items():
        if old in excluded or '/libjamesdsp.so' in old:
            continue
        if old.startswith('common/files/JamesDSP/'):
            new = old.replace('common/files/JamesDSP/', 'common/files/LightningDSP/', 1)
        else:
            new = rename.get(old, old)
        result[new] = mode
    extra = {
        'TEMP-ROOT-RELOAD.md': 0o100644,
        'SAMSUNG-RECOVERY.md': 0o100644,
        'LIGHTNINGDSP-CONTROL.md': 0o100644,
        'effect-host.sh': 0o100755,
        'audio-hal-recovery.sh': 0o100755,
        'aidl-audio-recovery.sh': 0o100755,
        'aidl-effect-mount.sh': 0o100755,
        'manual-audio-reload.sh': 0o100755,
        'native-control.sh': 0o100755,
        'lightningdsp-app-start.sh': 0o100755,
        'dsp-thread-profile.sh': 0o100755,
        'native-control/ldsp-candidate.json': 0o100644,
        'native-control/ldsp-build-provenance.json': 0o100644,
        'native-control/ldsp-NOTICES.txt': 0o100644,
        'native-control/global-service.rule': 0o100644,
        'native-control/default-label-opt-in.rule': 0o100644,
        DRIVER: 0o100644,
        HELPER: 0o100755,
    }
    result.update(extra)
    # Root-only distribution: one rebranded app, one matching dual-entry ARM64 driver.
    for stale in ('common/files/LightningDSP.apk', 'common/files/LightningDSP.apk.meta'):
        result.pop(stale, None)
    result[APP] = 0o100644
    result['common/files/LightningDSP.apk.meta'] = 0o100644
    return result


def build(output, root=ROOT):
    manifest = verify_candidate(root)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip()
    if branch not in ('master', 'ldsp-rebrand'):
        raise ValueError('LightningDSP packaging is limited to master or ldsp-rebrand')
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = payloads()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for name, mode in sorted(entries.items()):
            path = root / name
            if not path.is_file():
                raise ValueError('Missing distributable payload: ' + name)
            info = ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes())
    archive_hash = digest(output)
    output.with_suffix('.zip.sha256').write_text(f'{archive_hash}  {output.name}\n')
    output.with_suffix('.zip.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return archive_hash


if __name__ == '__main__':
    target = ROOT / 'dist' / f'LightningDSP-{VERSION}.zip'
    print(build(target))
