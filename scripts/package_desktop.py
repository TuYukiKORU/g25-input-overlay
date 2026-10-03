"""Create the downloadable folder-based Windows release and checksums."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import sys
from importlib import metadata

ROOT = Path(__file__).resolve().parents[1]


def friendly_manual(language):
    html = (ROOT / "docs" / f"manual-{language}.html").read_text(encoding="utf-8")
    return html.replace('href="manual-ja.html"', 'href="使い方_日本語.html"').replace(
        'href="manual-en.html"', 'href="User_Manual_English.html"')


def dependency_notices(folder):
    target = folder / "third-party-licenses"
    target.mkdir(exist_ok=True)
    names = ['Flask', 'Werkzeug', 'Jinja2', 'MarkupSafe', 'itsdangerous', 'click', 'blinker',
             'pywebview', 'proxy_tools', 'typing_extensions', 'pythonnet', 'clr_loader',
             'cffi', 'pycparser', 'pyinstaller']
    lines = ['# Third-party notices', '', 'License texts copied from the installed build dependencies.', '']
    for name in names:
        distribution = metadata.distribution(name)
        candidates = [p for p in distribution.files or [] if '.dist-info/' in str(p)
                      and Path(str(p)).name.lower().startswith(('license', 'copying'))]
        for index, path in enumerate(candidates):
            filename = f"{name}-{index + 1}-{Path(str(path)).name}"
            shutil.copy2(distribution.locate_file(path), target / filename)
        lines.append(f"- {name} {distribution.version}: {distribution.metadata.get('Home-page') or distribution.metadata.get('Project-URL') or 'see package metadata'}")
    shutil.copy2(ROOT / "docs/licenses/proxy_tools-LICENSE.txt", target / "proxy_tools-LICENSE.txt")
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", target / "Python-LICENSE.txt")
    (folder / "THIRD_PARTY_NOTICES.md").write_text('\n'.join(lines) + '\n', encoding="utf-8")


def package(version):
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", version):
        raise ValueError("Version must be safe for a filename")
    folder = ROOT / "dist" / "F1 Telemetry"
    if not (folder / "F1 Telemetry.exe").is_file():
        raise ValueError("Build the executable first")
    dependency_notices(folder)
    shutil.copy2(ROOT / "docs" / "LAPTOP_TEST.md", folder / "START HERE.md")
    shutil.copy2(ROOT / "docs" / "LAPTOP_TEST_JA.md", folder / "はじめに.md")
    for name in ("RELEASE_REVIEW.md", "リリース前レビュー_日本語.md"):
        if (ROOT / "docs" / name).exists():
            shutil.copy2(ROOT / "docs" / name, folder / name)
    for name in ("manual-en.html", "manual-ja.html", "PERFORMANCE.md", "performance-results.json"):
        shutil.copy2(ROOT / "docs" / name, folder / name)
    (folder / "使い方_日本語.html").write_text(friendly_manual("ja"), encoding="utf-8")
    (folder / "User_Manual_English.html").write_text(friendly_manual("en"), encoding="utf-8")
    (folder / "最初にお読みください.md").write_text(
        "# F1テレメトリー — 初回配布プレビュー\n\n"
        f"バージョン：{version}\n\n"
        "1. ZIPは全体を展開します。F1 Telemetry.exe と _internal は同じフォルダーに置きます。\n"
        "2. ゲームなしで試す：過去ラップで試す.cmd\n"
        "3. 新しい走行を記録：自分の走行を記録.cmd\n"
        "4. 詳しい説明：使い方_日本語.html（英語版：User_Manual_English.html）\n\n"
        "画面上部で日本語／Englishを切り替えられます。\n"
        "初回は はじめに.md の起動手順とWindowsの注意点も確認してください。\n"
        "ノートPC・実ゲームでの検証は未完了のプレビューです。\n", encoding="utf-8")
    (folder / "Test previous laps.cmd").write_text('@echo off\nstart "" "%~dp0F1 Telemetry.exe" --demo\n', encoding="ascii")
    (folder / "Open my recordings.cmd").write_text('@echo off\nstart "" "%~dp0F1 Telemetry.exe"\n', encoding="ascii")
    shutil.copy2(folder / "Test previous laps.cmd", folder / "過去ラップで試す.cmd")
    shutil.copy2(folder / "Open my recordings.cmd", folder / "自分の走行を記録.cmd")
    releases = ROOT / "releases"
    releases.mkdir(exist_ok=True)
    base = releases / f"F1-Telemetry-{version}-windows-x64"
    archive = Path(shutil.make_archive(str(base), "zip", root_dir=ROOT / "dist", base_dir="F1 Telemetry"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    japanese = releases / f"F1テレメトリー_初回配布版_v{version.split('-')[0]}_プレビュー_Windows64bit.zip"
    shutil.copy2(archive, japanese)
    japanese.with_suffix(".sha256").write_text(f"{digest}  {japanese.name}\n", encoding="utf-8")
    import zipfile
    manual_zip = releases / f"F1テレメトリー_使い方マニュアル_日本語・英語_v{version.split('-')[0]}.zip"
    with zipfile.ZipFile(manual_zip, "w", zipfile.ZIP_DEFLATED) as bundle:
        for language, name in (("ja", "使い方_日本語.html"), ("en", "User_Manual_English.html")):
            bundle.writestr(name, friendly_manual(language).encode("utf-8"))
        for name in ("PERFORMANCE.md", "performance-results.json"):
            bundle.write(ROOT / "docs" / name, name)
        if (ROOT / "docs/リリース前レビュー_日本語.md").exists():
            bundle.write(ROOT / "docs/リリース前レビュー_日本語.md", "リリース前レビュー_日本語.md")
    print(f"Release: {archive}\nSize: {archive.stat().st_size / 1024 / 1024:.1f} MB\nSHA256: {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.3.2-udp-preview")
    package(parser.parse_args().version)
