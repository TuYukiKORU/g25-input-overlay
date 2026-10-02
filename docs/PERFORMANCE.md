# Desktop performance check — 2026-10-02

These measurements were taken with the 0.3.0 source desktop app. They are not a new benchmark of the 0.3.1 packaged EXE.

Measured on Ryzen 5 3600, 12 logical CPUs, 32 GB RAM. Source desktop app and every child WebView2 process were included; the replay injector was excluded. Each phase ran for 30 seconds after startup warm-up. CPU percentages refer to the whole PC.

| Condition | Average CPU | CPU p95 | Brief CPU peak | Average private RAM | Peak private RAM | Peak summed working set |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Idle | 0.17% | 0.77% | 1.28% | 309 MiB | 315 MiB | 543 MiB |
| Recording 60 Hz | 0.17% | 0.77% | 1.02% | 305 MiB | 307 MiB | 542 MiB |
| Minimized 60 Hz | 0.16% | 0.51% | 1.28% | 278 MiB | 302 MiB | 536 MiB |
| Recording 120 Hz | 0.76% | 2.31% | 9.47% | 317 MiB | 364 MiB | 576 MiB |
| Session analysis + 60 Hz | 0.32% | 1.02% | 5.64% | 366 MiB | 369 MiB | 585 MiB |

Five full 22-car packet types were sent at 60/120 Hz, plus session/setup/damage at 1 Hz, using actual recorded Bahrain player samples. This is a constructed stream, not a raw game-packet capture. The isolated UDP port left the existing receiver untouched. All eight packet groups were receiving in each replay phase. Minimized WebView reported document.hidden=true.

Completed lap saving was verified: 37 to 38 stored laps, 1,426,834 bytes in the new lap JSON. Session analysis completed successfully, with a fresh saved result; it took approximately 0.33 seconds, so the 30-second average understates that brief computation. Normal app shutdown returned 0.

Private RAM is process-private memory; summed working sets include shared pages and may count some pages more than once. Seven processes were typically present (briefly eight). Larger sessions or more windows can increase memory. The 120 Hz run crossed a lap boundary and briefly peaked near 9.5% CPU, so its average is not a pure packet-rate comparison.

Game FPS, game frame times and GPU usage were not measured. A laptop/in-game check remains necessary. The numbers describe the source desktop window with the same app/engine. The new unsigned packaged EXE also passed functional window checks on this PC, but was not separately profiled. Older unsigned builds were blocked by Smart App Control; other PCs can still block unsigned releases.

Final touches: unchanged lap lists no longer rebuild their controls; hidden-page lap polling pauses and refreshes on return; overlapping polls are prevented; chart hover/resize redraws are batched; manuals are linked in the toolbar; additional comparison insights are translated. No statistically significant before/after improvement is claimed from these short runs.

For gaming, use one recording window at 60 Hz, minimize when not viewing, and run heavier manual analyses between stints. Recording continues independently of UI polling.

Reproduce with the build Python: install psutil from PyPI, then run scripts/benchmark_desktop.py --output .runtime/performance-new --seconds 30. The output directory must be new. Do not include the benchmark dependency in production requirements.
