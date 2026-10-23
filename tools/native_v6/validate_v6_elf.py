#!/usr/bin/env python3
# Copyright (C) 2026 LightningDSP contributors
# SPDX-License-Identifier: Apache-2.0
"""Inspect, never execute, V6 ARM64 artifacts. Passing is not device validation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

PROFILE = Path(__file__).with_name('v6-profile.json')
FACTORY = {'createEffect', 'queryEffect', 'destroyEffect', 'AELI'}


def load_fingerprint(data):
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    if header[1] != 3 or header[2] != 183:
        raise ValueError('Expected AArch64 ET_DYN (driver or PIE helper)')
    phoff, phsize, count = header[5], header[9], header[10]
    if phsize != 56 or not 1 <= count <= 256 or phoff + count * phsize > len(data):
        raise ValueError('Invalid ELF program-header bounds')
    digest = hashlib.sha256()
    loads = 0
    for i in range(count):
        ph = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize)
        if ph[0] != 1:  # PT_LOAD only: stripping may remove non-loaded symbols.
            continue
        offset, size = ph[2], ph[5]
        if offset + size > len(data) or size > ph[6]:
            raise ValueError('Invalid PT_LOAD bounds')
        segment = bytearray(data[offset:offset + size])
        if offset == 0 and size >= 64:
            segment[40:48] = b'\0' * 8  # e_shoff
            segment[58:64] = b'\0' * 6  # section-header metadata
        digest.update(struct.pack('<IIQQQQQQ', *ph))
        digest.update(segment)
        loads += 1
    if not loads:
        raise ValueError('ELF has no load segments')
    return digest.hexdigest()


def dynamic_info(text):
    needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)
    soname = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', text)
    nodelete = any('NODELETE' in line for line in text.splitlines() if '(FLAGS_1)' in line)
    return needed, soname, nodelete


def defined_exports(text):
    exports = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].rstrip(':').isdigit():
            if fields[4] in ('GLOBAL', 'WEAK') and fields[5] in ('DEFAULT', 'PROTECTED') and fields[6] != 'UND':
                exports[fields[7]] = fields[3]
    return exports


def verify_dynamic(text, symbols, allowed, driver):
    needed, sonames, nodelete = dynamic_info(text)
    if not needed or len(needed) != len(set(needed)):
        raise ValueError('Missing or duplicate runtime dependencies')
    extra = set(needed) - set(allowed)
    if extra:
        raise ValueError('Forbidden runtime dependencies: ' + ', '.join(sorted(extra)))
    if not {'libbinder_ndk.so', 'libc.so'} <= set(needed):
        raise ValueError('Required system Binder/libc dependencies missing')
    if driver:
        if sonames != ['liblightningdsp_v6.so']:
            raise ValueError('Unexpected V6 SONAME')
        if not nodelete:
            raise ValueError('Missing DF_1_NODELETE lifetime protection')
        exports = defined_exports(symbols)
        if set(exports) != FACTORY:
            raise ValueError('Factory export surface differs: ' + ', '.join(sorted(exports)))
        wrong_types = {name: exports[name] for name in FACTORY
                       if exports[name] != ('OBJECT' if name == 'AELI' else 'FUNC')}
        if wrong_types:
            raise ValueError('Factory export symbol types differ: ' + ', '.join(
                f'{name}={kind}' for name, kind in sorted(wrong_types.items())))
    return {'direct_dt_needed': needed, 'soname': sonames, 'nodelete': nodelete}


def verify_embedded_symbols(text):
    required = ('aidl::android::hardware::audio::effect::BnEffect::',
                'aidl::android::hardware::audio::effect::EffectImpl::',
                'aidl::android::hardware::audio::effect::Descriptor::',
                'aidl::android::media::audio::common::')
    missing = [name for name in required if name not in text]
    if missing or 'readFromParcel(' not in text or 'writeToParcel(' not in text:
        raise ValueError('Embedded interface/implementation symbol evidence missing: ' + ', '.join(missing))


def read_artifact(path):
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('Artifact exceeds inspection size bound')
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--unstripped-driver', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--readelf', required=True)
    parser.add_argument('--nm', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_commit):
        parser.error('source-commit must be a full SHA-1, not a branch or abbreviated commit')
    profile = json.loads(PROFILE.read_text())
    report = {'iteration': 6, 'profile': profile['profile'], 'controlProtocol': 3,
              'state': 'elf-validated-runtime-unverified',
              'source': {'commit': args.source_commit,
                         'aospManifestSha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest()},
              'artifacts': {}}
    driver_data = read_artifact(args.driver)
    unstripped_data = read_artifact(args.unstripped_driver)
    fingerprint = load_fingerprint(driver_data)
    if load_fingerprint(unstripped_data) != fingerprint:
        raise ValueError('Unstripped driver does not match the loadable driver contents')
    embedded = subprocess.check_output([args.nm, '--defined-only', '--demangle', str(args.unstripped_driver)], text=True)
    verify_embedded_symbols(embedded)
    for kind, path in (('driver', args.driver), ('helper', args.helper)):
        data = read_artifact(path)
        load_fingerprint(data)
        dynamic = subprocess.check_output([args.readelf, '--dynamic', '--wide', str(path)], text=True)
        symbols = subprocess.check_output([args.readelf, '--dyn-syms', '--wide', str(path)], text=True)
        value = verify_dynamic(dynamic, symbols, profile[kind + 'AllowedNeeded'], kind == 'driver')
        if read_artifact(path) != data:
            raise ValueError('Artifact changed during inspection: ' + path.name)
        value.update(sha256=hashlib.sha256(data).hexdigest(), sizeBytes=len(data), file=path.name)
        report['artifacts'][kind] = value
    if read_artifact(args.driver) != driver_data or read_artifact(args.unstripped_driver) != unstripped_data:
        raise ValueError('Driver changed during embedding inspection')
    report['embeddedCodeEvidence'] = {
        'definedSymbolsVerified': True, 'loadSegmentsSha256': fingerprint,
        'unstrippedSha256': hashlib.sha256(unstripped_data).hexdigest()}
    # Write only after all gates pass. Do not include local/private source paths.
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('V6 ELF gates passed; Android factory/Binder/audio behavior remains unverified')


if __name__ == '__main__':
    main()
