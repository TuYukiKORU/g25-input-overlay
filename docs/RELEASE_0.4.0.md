# F1 Telemetry 0.4.0-preview

Windows x64 preview prepared on 2026-10-06.

## Changes

- Session labels: track, Practice/Qualifying/Race/Time Attack, saved lap count, date/time, ID.
- Race starting battery in 10% steps; qualifying uses Overtake, starts at 100% and targets 0%, with inferred energy clearly labeled.
- Corrected Strategy map orientation and added ERS practice targets for collecting comparable control and deployment laps.
- Flashback recording retains valid prefixes and backs up revised completed laps.
- Lap replay aligns both cars at a shared starting position, supports playback/scrubbing/zoom and excludes impossible position jumps from maps.
- Faster saved-session navigation and less work on the telemetry receiver at lap completion.
- Updated offline English/Japanese manuals and contributor validation guidance.

## Verification and limits

- 270 Python tests and 11 JavaScript replay tests passed. JavaScript syntax, dependency consistency and Git whitespace checks passed.
- Built with PyInstaller 6.22.3, pywebview 6.2.1 and Flask 3.1.3. The bundled demo remains separate from personal recordings and disables UDP reception.
- The new unsigned executable's launch check was blocked by Windows Application Control on the development PC. Its native window is unverified; do not disable Windows protections to run it. Use a trusted signed build where your Windows policy requires one.
- Source-browser workflows were checked during development. Laptop compatibility, actual game flashback behavior and predictive ERS accuracy still need in-game validation.
- The included performance report is the historical 0.3.0 source desktop measurement, not a benchmark of this EXE. Recent receiver timings in CHANGELOG.md measure recorder operations, not game FPS.

## Run

Extract the entire ZIP. Keep `F1 Telemetry.exe` and `_internal` together. Use `Test previous laps.cmd` / `過去ラップで試す.cmd` for the isolated real-lap demo, or `Open my recordings.cmd` / `自分の走行を記録.cmd` for recording. Microsoft Edge WebView2 Runtime is required; Python is not.

個人の走行記録は同梱していません。過去ラップのデモは別コピーで、UDP記録を無効にします。本EXEは開発PCのWindows Application Controlで起動をブロックされ、実ウィンドウの確認は未完了です。保護機能を無効にせず、必要なPCでは信頼できる署名済み版を使用してください。詳細は `使い方_日本語.html` を参照してください。
