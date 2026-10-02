# F1 Telemetry — laptop test

Full user manuals are included as **manual-en.html** and **manual-ja.html**. They open offline in a browser, support printing/PDF saving, and cover all pages, recording, comparison evidence, backups and troubleshooting. The desktop toolbar also has a **User manual** link. See **PERFORMANCE.md** for the measured load and its limits.

Windows x64 bilingual test build, version 0.3.1-laptop-preview.

The selected, comparison and fastest lap boxes now share aligned labels, equal
widths and a 48px height on desktop. On narrow screens they wrap into aligned rows.
The layout was checked in English and Japanese at 1280, 768 and 375px widths.

**Validation:** The actual packaged EXE passed on the development PC: dark File menu,
37 laps, charts, notes, language switching, all eight app pages and both manuals.
The source-window check and 131 regression tests also passed. This is still an
unsigned preview; the laptop/game checklist remains necessary. Previous builds
were blocked by Smart App Control here, and other PCs may enforce different trust
policies. Unblocking a ZIP does not fix an App Control signing-policy block.

日本語の説明は同梱の **はじめに.md** を参照してください。

## Language

Use **Language / 言語** at the top of any page to choose **日本語** or **English**.
The screen updates without reloading, preserving lap selection and unsaved notes.
The desktop app saves the language for the next launch, independently of its local
server port. The first launch follows the Windows display language. The dark
**File / ファイル** menu inside the app follows the selected language. Saved telemetry, notes, numbers and
units remain unchanged.

## Open the app

1. Copy the Windows ZIP to the laptop. Before extracting, right-click the ZIP,
   choose **Properties**, tick **Unblock** if shown, and click **Apply**.
   Then **extract the entire ZIP** into a fresh folder.
2. Open the extracted `F1 Telemetry` folder.
3. Double-click **Test previous laps.cmd** for a game-free test.
4. To record new laps, double-click **F1 Telemetry.exe** (or **Open my recordings.cmd**).

Keep `_internal` beside the executable. Python does not need to be installed. The
window uses Microsoft Edge WebView2 Runtime. If the app reports that it is missing,
install the **Evergreen Standalone Installer, x64** from:
https://developer.microsoft.com/en-us/microsoft-edge/webview2/

This is an unsigned test build; Windows may show an unknown-publisher prompt.
Only run the package received from the project owner.

### If you see `Failed to resolve Python.Runtime.Loader.Initialize`

Windows can mark the bundled DLLs as downloaded from the internet and prevent
the window component from loading. This exact error was reproduced in the
packaged app by adding that marker; removing it restored startup.

Close the app, unblock the original ZIP as described above, and extract it into
a **new folder**. Launch the new copy. Unblocking the ZIP after extraction does
not clear markers already attached to the extracted files. If the ZIP has no
Unblock checkbox or the error remains, share `%LOCALAPPDATA%\F1Telemetry\logs\desktop.log`
so the actual runtime failure can be checked.

## Included real test laps

The test data contains 37 laps copied from the owner's saved sessions, with all
recorded telemetry samples and available setup snapshots. Personal lap notes and
old analysis caches are omitted. Lap times, missing laps, invalid laps, unknown
conditions and unknown track names are preserved.

| Session | Track | Laps | Valid laps |
| --- | --- | ---: | ---: |
| 2026-08-25 | Bahrain, Practice 1 | 7 | 5 |
| 2026-08-14 | COTA, Race | 22 | 20 |
| 2026-09-11 | Unknown Track 42, Time Trial | 8 | 1 |

Track 42 stays unknown because the current project does not identify that track.
Invalid laps stay invalid. These are actual recordings, not simulated ideal laps.
The dataset manifest and SHA256 fingerprints are in `_internal/test-laps/manifest.json`.

Test mode never binds the game's UDP port. Notes, corner edits and analyses affect
only the writable test copy. Recording mode starts with an empty recordings folder
on a new laptop. Use **File → Open test laps / Open my recordings** to open the other
mode in a separate window.

## Test checklist

- Confirm the window says **Test laps — recording off**, and the page shows the test banner.
- Use the Session selector to check all three sessions and their lap counts.
- In Bahrain, select a valid lap and another valid comparison lap. Confirm the speed,
  inputs, map and comparison panels render and change when you select a different lap.
- In COTA, inspect the stint dashboard and toggle **Include pit and invalid laps**.
- Open **Session analysis**, select Bahrain or COTA, and start analysis. Wait for completion.
  Open a different page and return to confirm the saved result is available.
- Try **Qualifying strategy**, **Operation Library** and **ERS Strategy**. Missing
  evidence is allowed; report crashes, stuck loading states or incorrect selections.
- Save a note on a test lap. Close the window, reopen test mode, and confirm the note persists.
- Resize the window to your normal laptop size and check that controls remain usable.
- Close both modes. Confirm their windows and processes exit.
- Switch Japanese → English → Japanese, and confirm lap selection and an unsaved
  note stay unchanged. Reopen the app to confirm the language is remembered.

## Record a new lap (optional second test)

Close any older browser-based telemetry receiver first; only one receiver can use
UDP 20777. Open **F1 Telemetry.exe** and configure the game's UDP destination as
`127.0.0.1`, port `20777`, if the game runs on the same laptop. For a game on another
device, use the laptop's LAN IP as the destination and allow the app to receive UDP
on the private network. Select the game's appropriate UDP format.

Complete a lap and cross the line into the next lap. Confirm the completed lap
appears, then close and reopen the app to confirm it was saved. An unfinished lap
is not saved merely by closing the window.

## Data and troubleshooting

The normal location is `%LOCALAPPDATA%\F1Telemetry\`:

- `sessions`: your new recordings and analyses.
- `test-laps-v1`: a separate first-run copy of the bundled test dataset.
- `logs\desktop.log`: startup and application errors; logs rotate automatically.
- `preferences.json`: the selected interface language.
- `webview` / `webview-test`: separate window settings for the two modes.

Use **File → Open recordings folder / Open logs folder** to find these locations.
Moving or replacing the extracted app folder preserves saved data. Test-mode edits
also persist. To reset test data, close the app and rename `test-laps-v1` to a backup
name; the next test launch copies the original bundled dataset again.

If startup says UDP 20777 is in use, stop the other telemetry app first. If a mode
is already open, switch to its existing window. If a page fails, share the relevant
log entries and describe the session/lap and action that failed.

This build has been checked on the development PC. The laptop checklist verifies
compatibility on a second PC without the source checkout or a Python installation.
