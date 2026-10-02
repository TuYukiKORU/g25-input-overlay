"""Verify Japanese release downloads still contain the reviewed executable."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check():
    release = ROOT / 'releases/F1テレメトリー_初回配布版_v0.3.1_プレビュー_Windows64bit.zip'
    manuals = ROOT / 'releases/F1テレメトリー_使い方マニュアル_日本語・英語_v0.3.1.zip'
    reviewed = json.loads((ROOT / '.runtime/初回配布_再確認/review-results.json').read_text(encoding='utf-8'))
    assert reviewed['ok']
    prefix = 'F1 Telemetry/'
    with zipfile.ZipFile(release) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        for name in ('使い方_日本語.html', 'User_Manual_English.html', '最初にお読みください.md',
                     'リリース前レビュー_日本語.md', 'RELEASE_REVIEW.md', 'THIRD_PARTY_NOTICES.md',
                     'third-party-licenses/Python-LICENSE.txt', 'third-party-licenses/proxy_tools-LICENSE.txt'):
            assert prefix + name in names, name
        assert not any(name.endswith(('.log', '.lock')) or '/lap-notes/' in name for name in names)
        exe = archive.read(prefix + 'F1 Telemetry.exe')
        assert hashlib.sha256(exe).hexdigest() == reviewed['exe_sha256']
        data_prefix = prefix + '_internal/test-laps/'
        manifest = json.loads(archive.read(data_prefix + 'manifest.json'))
        fingerprints = next(v for v in manifest.values() if isinstance(v, dict) and len(v) == 52)
        for name, digest in fingerprints.items():
            assert hashlib.sha256(archive.read(data_prefix + name)).hexdigest() == digest, name
        laps = [name for name in names if name.startswith(data_prefix) and '/laps/lap_' in name]
        assert len(laps) == 37
        for language in ('en', 'ja'):
            assert archive.read(prefix + f'_internal/frontend/static/manual-{language}.html') == (ROOT / f'docs/manual-{language}.html').read_bytes()
    with zipfile.ZipFile(manuals) as archive:
        assert archive.testzip() is None
        for language, name in (('ja', '使い方_日本語.html'), ('en', 'User_Manual_English.html')):
            html = archive.read(name).decode('utf-8')
            assert f'<html lang="{language}">' in html
            assert '0.3.1-laptop-preview' in html
            assert html.count('<section ') == 8
            assert 'href="使い方_日本語.html"' in html
            assert 'href="User_Manual_English.html"' in html
            assert 'href="manual-ja.html"' not in html
            assert archive.getinfo(name).flag_bits & 0x800 or name.isascii()
    result = {'ok': True, 'reviewed_exe_unchanged': True, 'test_laps': len(laps),
              'verified_data_files': len(fingerprints), 'downloads': [
                  {'name': path.name, 'bytes': path.stat().st_size,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in (release, manuals)]}
    (ROOT / '.runtime/final-download-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Final downloads passed: reviewed EXE unchanged; 37 laps; 52 fingerprints; Japanese names and manuals verified.')


if __name__ == '__main__':
    check()
