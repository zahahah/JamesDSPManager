#!/usr/bin/env python3
"""Replace misleading 1.6.15 root-effect failure text in an apktool decode.

This changes resources only. It does not turn a missing AIDL descriptor into an
available effect, and it must not be used to bypass effect creation checks.
"""

import argparse
from pathlib import Path
import re
from xml.sax.saxutils import escape


ENGLISH = {
    "load_fail_header": "JamesDSP effect not detected",
    "load_fail_card_title": "Audio effect unavailable",
    "load_fail_card": (
        "The app cannot confirm that Android registered the JamesDSP effect. "
        "The module can be mounted for the audio service while its files are hidden "
        "from this app. Do not assume audio processing is active."
    ),
    "load_fail_arch_card_title": "Module already mounted?",
    "load_fail_arch_card": (
        "Check the module status and audio-effect factory diagnostics. "
        "Reinstalling the app alone cannot register an effect in the audio service."
    ),
}

PORTUGUESE = {
    "load_fail_header": "Efeito JamesDSP não detectado",
    "load_fail_card_title": "Efeito de áudio indisponível",
    "load_fail_card": (
        "O app não consegue confirmar que o Android registrou o efeito JamesDSP. "
        "O módulo pode estar montado para o serviço de áudio, mas invisível para "
        "este app. Não presuma que o áudio esteja sendo processado."
    ),
    "load_fail_arch_card_title": "Módulo já montado?",
    "load_fail_arch_card": (
        "Verifique o status do módulo e o diagnóstico da fábrica de efeitos. "
        "Reinstalar somente o app não registra o efeito no serviço de áudio."
    ),
}


def patch_strings(resources: Path) -> int:
    changed = 0
    for path in resources.glob("values*/strings.xml"):
        values = PORTUGUESE if path.parent.name.startswith("values-pt") else ENGLISH
        original = path.read_text()
        updated = original
        for name, message in values.items():
            pattern = rf'(<string name="{name}")(?: [^>]*)?>.*?</string>'
            replacement = rf'\1>{escape(message)}</string>'
            updated, count = re.subn(pattern, replacement, updated, count=1)
            if not count and path.parent.name == "values":
                raise ValueError(f"Required string {name} missing from {path}")
        if updated != original:
            path.write_text(updated)
            changed += 1
    if not changed:
        raise ValueError(f"No strings.xml files patched under {resources}")
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("decoded_apk", type=Path)
    args = parser.parse_args()
    print(f"Patched {patch_strings(args.decoded_apk / 'res')} locale resources")
