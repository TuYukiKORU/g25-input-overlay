"""Review the real packaged EXE from a Japanese path using disposable data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import socket
import struct
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def validate(archive, output):
    output.mkdir(parents=True, exist_ok=False)
    extracted = output / '友人向け アプリ'
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        names = bundle.namelist()
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
        assert len([n for n in names if '/test-laps/' in n and '/laps/lap_' in n]) == 37
        assert not any(n.endswith(('.log', '.lock', '.py', '.pyc')) or 'psutil' in n.lower() for n in names)
        bundle.extractall(extracted)
    app_folder = extracted / 'F1 Telemetry'
    exe = app_folder / 'F1 Telemetry.exe'
    raw = exe.read_bytes()
    offset = struct.unpack_from('<I', raw, 0x3c)[0]
    assert raw[:2] == b'MZ' and raw[offset:offset+4] == b'PE\0\0'
    assert struct.unpack_from('<H', raw, offset+4)[0] == 0x8664
    report = {'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
              'exe_sha256':hashlib.sha256(raw).hexdigest(), 'machine':'Windows x64',
              'zip_integrity':True, 'test_laps':37, 'startup_path':'Japanese characters and spaces',
              'bundle_metadata':json.loads((app_folder/'_internal/build-info.json').read_text(encoding='utf-8'))}
    home = output / '確認用データ'
    main_report = output / '起動確認.json'
    def start(report_path, demo=True):
        command = [str(exe), '--data-dir', str(home), '--smoke-report', str(report_path)]
        if demo:
            command.append('--demo')
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    process = start(main_report)
    print('Packaged window launched from Japanese/spaced path', flush=True)
    deadline = time.monotonic() + 40
    log = home/'logs/desktop.log'
    while process.poll() is None and time.monotonic()<deadline:
        if log.exists() and 'Starting Test laps' in log.read_text(encoding='utf-8'):
            break
        time.sleep(.1)
    duplicate_report = output/'重複起動.json'
    duplicate = start(duplicate_report)
    duplicate.wait(20)
    error = read(duplicate_report)
    assert duplicate.returncode == 1 and 'already open' in error.get('error',''), error
    report['duplicate_mode_rejected'] = True
    process.wait(120)
    main = read(main_report)
    assert process.returncode == 0 and main['ok'] and main['frozen'], main
    report['window'] = main
    print('Window, languages, notes, strategies, manuals and duplicate-mode checks passed', flush=True)
    # A user edit in the demo copy must survive another launch and retain Unicode.
    lap = next((home/'test-laps-v1').glob('*track-3/**/lap_008.json'))
    saved = read(lap)
    marker = '再起動後も残る日本語メモ'
    saved['note'] = marker
    lap.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
    restarted_report = output/'再起動確認.json'
    restarted = start(restarted_report)
    restarted.wait(120)
    restarted_value = read(restarted_report)
    assert restarted.returncode == 0 and restarted_value['ok'], restarted_value
    assert restarted_value['initial_language'] == 'ja'
    assert read(lap)['note'] == marker
    assert not (home/'sessions').exists()
    report['language_and_japanese_note_persist'] = True
    report['test_copy_isolated_from_live_recordings'] = True
    report['restart'] = restarted_value
    # Reserve only if no receiver already owns the game's port. Never stop it.
    reservation = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            reservation.bind(('0.0.0.0', 20777))
        except OSError as error:
            if error.winerror != 10048:
                raise
        conflict_report = output/'ポート競合.json'
        conflict = start(conflict_report, demo=False)
        conflict.wait(20)
        value = read(conflict_report)
        assert conflict.returncode == 1 and 'UDP 20777 is already in use' in value.get('error',''), value
        report['port_conflict_rejected'] = True
    finally:
        reservation.close()
    report['ok'] = True
    (output/'review-results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Release review passed: '+str(output/'review-results.json'), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validate(args.archive.resolve(), args.output.resolve())
