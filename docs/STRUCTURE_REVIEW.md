# Structure review for desktop distribution

The existing project has useful boundaries: UDP parsing, lap recording, storage,
analysis algorithms and background workers are already separate modules. Keep
those boundaries as the app gains desktop support.

## Changes included in this build

- `desktop.py` owns the native window, local HTTP server, UDP socket and shutdown.
  The source browser launcher remains available. The desktop server uses a free
  loopback port; UDP reception keeps the game's configured port 20777.
- The dark File menu lives in `desktop.js`, alongside the language selector.
  A narrow desktop bridge exposes only four fixed actions: switch mode, open the
  recording folder, open the log folder and close. It accepts no arbitrary paths
  or commands. Native title-bar controls remain available.
- `backend/runtime_paths.py` resolves read-only bundled assets independently of
  the working directory. Templates and static files work after moving the package.
- Writable recordings, test copies, logs and WebView profiles live in the Windows
  user's Local AppData folder, outside the executable and source checkout.
- `scripts/prepare_test_laps.py` makes a bounded, reproducible real-lap dataset with
  setup snapshots, regenerated best-lap references and a checksum manifest.
- Source-based analysis-rule checks use a build fingerprint in the executable.
  Cached analyses can still detect rule changes across app updates.
- Desktop shutdown stops incoming telemetry and drains queued completed-lap writes.
- A file lock prevents duplicate instances of each mode; test mode and recording
  mode have separate folders, windows and WebView profiles.
- `F1Telemetry.spec`, build metadata, packaging scripts and laptop instructions
  make the release repeatable. Build environments, runtime data, recordings and
  generated releases are excluded from Git.
- A shared English/Japanese catalog translates display text on the legacy pages.
  Desktop language preferences are written atomically outside the executable, so
  the random local HTTP port does not affect persistence. Saved notes, numeric
  telemetry and API identifiers are excluded from translation. New screens should
  use explicit translation keys as feature modules are gradually extracted.

## Gaming footprint and final polish

The runtime keeps recording independent of page refreshes. Hidden pages stop lap-list polling; unchanged responses skip control rebuilds; requests do not overlap; hover and resize redraws use animation-frame batching. Offline manuals are served by a bounded language route and bundled with the release. The benchmark tool and its psutil dependency stay outside the production entry point. See PERFORMANCE.md for measurements, brief peaks and the laptop/FPS validation boundary.

## Recommended next improvements

1. **Introduce an application factory.** `backend/app.py` currently creates storage
   and starts background workers when imported. A `create_app(storage, services)`
   factory would make dependencies and lifecycle explicit, simplify tests, and
   allow changing data workspaces without starting a second process. This deserves
   its own change with API regression checks.
2. **Split routes by feature.** `analysis_routes.py` already uses a Flask blueprint;
   use that pattern for lap browsing, session analysis, track definitions and ERS
   endpoints. Keep orchestration in routes and computations in their current modules.
3. **Split the largest frontend files by responsibility.** `analysis.js` handles
   selection, requests, chart drawing, maps and insights together. Extract request
   helpers and graph/map rendering gradually. Move large inline styles from templates
   into CSS files. Preserve the current behavior while doing this.
4. **Add a saved-data format version and migrations.** Storage supports old and new
   directory layouts, while game telemetry adds fields over time. Explicit format
   versions and migrations will make compatibility across releases clearer. Back up
   data before any migration.
5. **Automate Windows release checks once the laptop passes.** Pin a tested build
   dependency set, build a ZIP on a Windows runner, and keep the executable smoke
   report with each candidate. Publish source and release ZIPs separately. Avoid
   committing personal recordings, logs, virtual environments or built binaries.

The application factory and route/frontend splits are recommendations for a later
refactor. They are not required to create this desktop package, and a broad rewrite
would make it harder to compare the laptop behavior with the current working app.
