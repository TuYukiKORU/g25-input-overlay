# Release review — 0.3.1-laptop-preview

Reviewed on 2026-10-02 on the development Windows PC. This release is ready for friends to try as a preview; laptop and in-game validation remain outstanding.

## Scope and findings

Reviewed the application source, desktop lifecycle and fixed window bridge actions, UDP receiver, lap persistence, analysis workers, localization, manuals, bundled data and distribution contents. Launched the actual packaged EXE twice from a folder containing Japanese characters and spaces, using disposable data separate from live recordings. This is an application review and functional verification, not a formal audit of every bundled third-party binary.

Fixed during review:

- Failed lap writes and full save queues previously could leave reception looking healthy. They now produce a persistent save-error indicator, a translated explanation and an exit warning. The writer survives ordinary write exceptions. Failed or dropped laps are not automatically recovered; correct disk/folder issues and restart before recording again.
- Added exact loopback Host and Origin checks, cross-site request rejection, a 1 MiB request limit, and frame/content-type response protections to the desktop server. These reduce unwanted browser requests; they do not authenticate arbitrary software already running on the PC.
- Clarified that qualifying/race strategy evidence requires at least two comparable valid **F1 26** laps.
- Added Japanese download filenames, an obvious Japanese quick-start file and Japanese manual filename. Included available dependency license texts and notices.

## Verification

- All **131 automated tests passed**, including save failures, queue overflow, request restrictions and payload limits.
- Actual Windows x64 EXE: startup, restart, duplicate-window rejection and occupied UDP-port reporting passed.
- The packaged app loaded all **37 previous laps**; four charts rendered. Language switching preserved selections and draft notes. Japanese settings and a Japanese saved note survived a restart.
- Eight Japanese app pages and both eight-section manuals loaded. Session analysis completed, and qualifying/race analysis completed with current saved results using suitable COTA F1 26 test laps.
- An unchanged lap list caused zero control rebuilds during the observed polling interval. Test data remained isolated from live recordings.
- Verified all **52 bundled test-data file fingerprints**. Release ZIP integrity, Windows x64 executable format and exclusion of runtime logs were checked. Personal note files and old analysis caches are excluded from the bundled test dataset.

Reviewed EXE SHA-256: `05b73e3ff2789c7e3103694b8338e6be6b4a6594010b8ab5ab1debfe3ad79da5`.

The ZIP also contains manuals, review reports, launchers and license notices. ZIP checksums are written beside the downloads; the executable hash above identifies the tested binary independently of documentation updates.

## Remaining checks and recommendations

1. Run the included laptop checklist and a real game recording before calling this a stable release. Game FPS/frame times, GPU load and another PC's Windows policy were not measured here. The earlier performance report describes the **0.3.0 source desktop window**, not a new 0.3.1 EXE benchmark.
2. The executable is **unsigned**. It launched on this PC, but Windows policy can block it elsewhere. Use a trusted signed build where required; do not disable Windows protections to distribute this preview.
3. Strategy suggestions still depend on comparable recorded evidence and are not proven optimal racing strategies. Missing conditions and recording gaps limit conclusions.
4. For repeatable releases, pin all build dependencies and add an automated Windows build and package smoke check. As development grows, move application startup into a factory and separate routes from services; this is a maintainability recommendation, not a release blocker.

References: [Flask web security](https://flask.palletsprojects.com/en/stable/web-security/), [pywebview security](https://pywebview.flowrl.com/guide/security.html), [Microsoft Smart App Control guidance](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions).
