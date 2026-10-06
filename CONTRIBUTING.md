# Contributing

This repository contains the source for the F1 telemetry lap-analysis app and its
Windows desktop build. Personal recordings, local settings, build environments,
and generated Windows release ZIPs are excluded from Git.

## Set up on Windows

Install Git and Python 3.12 or newer, then run these commands in PowerShell:

```powershell
git clone https://github.com/TuYukiKORU/g25-input-overlay.git
cd g25-input-overlay
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\Start-Telemetry.ps1
```

The launcher opens the analysis page at <http://127.0.0.1:5000/analysis>.
Use `STOP_OVERLAY.cmd` to stop the source app. For a sample lap without the game,
run `.\.venv\Scripts\python.exe scripts/generate_sample_lap.py` before starting.
Recordings are stored locally in `data/sessions/` and are ignored by Git.

Stop the source server with `STOP_OVERLAY.cmd` before launching the desktop
window. Install the desktop dependencies and start it with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop.py
```

The Windows desktop window also requires Microsoft Edge WebView2 Runtime.
See [README.md](README.md) and [docs/LAPTOP_TEST.md](docs/LAPTOP_TEST.md) for
game settings, app features, and desktop testing.

## Send a change

The repository owner can invite you through **Settings > Collaborators** to grant
direct push access. Accept the invitation before pushing. Public read access
alone does not grant permission to commit to this repository.

Create a branch for your change:

```powershell
git switch master
git pull --ff-only origin master
git switch -c feature/your-change
```

Validate the affected behavior using the [testing guidance](#testing) below.

Review and stage the intended files, commit, and push your branch:

```powershell
git diff
git status --short
git add path/to/changed-file
git commit -m "Describe the change"
git push -u origin feature/your-change
```

Open a pull request into `master` on GitHub. If you are not a collaborator, fork
the repository, push your branch to your fork, and open a pull request from there.
Keep personal sessions, notes, credentials, and runtime logs out of commits.

## Testing

Choose checks based on the change, rather than running the entire suite at the
end of every chat. Keep the existing tests; reduce unnecessary executions.
Review changed files and run `git diff --check -- path/to/changed-file`.

Use the smallest meaningful selection from these starting points. Trace callers
when a change can affect another subsystem; this table is not a requirement to
run every listed file for every edit.

| Change | Relevant checks |
| --- | --- |
| Documentation or UI copy | Review the edit and check the diff. No application tests. |
| Frontend layout or interaction | Check syntax of changed JavaScript and verify one affected browser workflow. Run `node --test tests/test_lap_replay.cjs` when replay calculations change. Python tests are needed only if backend behavior or a shared contract changes. |
| Lap recording, rewinds, or writer queue | `tests/test_recorder.py`; include the save-failure and queue-overflow cases in `tests/test_release_review.py` and `tests/test_desktop_runtime.py::test_completed_laps_are_flushed_before_shutdown` when writer or queue behavior changes. |
| UDP parsing | `tests/test_telemetry.py` and `tests/test_udp_packet_audit.py`; include recorder cases when decoded fields affect lap assembly. |
| Storage or caching | `tests/test_storage.py` plus affected consumer or cache-invalidation cases. |
| Lap comparison or session analysis | Affected cases in `tests/test_analysis.py`, `tests/test_session_analysis.py`, or `tests/test_workspace_insights.py`. |
| ERS strategy or practice suggestions | Affected cases in `tests/test_strategy_analysis.py`, `tests/test_strategy_workspace.py`, `tests/test_strategy_learning.py`, or `tests/test_ers_strategy.py`. |

For example, a change confined to the practice suggestion calculations can start
with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_strategy_learning.py
```

Use individual test names or `-k` to select relevant cases in a larger file.
Passing results remain valid until the relevant code changes. After fixing a
failure, rerun failed and affected checks; broaden testing only when a failure
or an identified dependency makes it necessary. Do not repeat a passing run
solely as an end-of-chat check.

Run the full Python suite for changes spanning multiple subsystems, shared data
or API contracts, dependencies, desktop lifecycle/security, or a release:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Run it once on the final relevant code. Avoid running overlapping targeted tests
again afterward unless something changes. Builds, packaged desktop launches,
and performance benchmarks belong to tasks that affect those areas, rather than
every change. Keep browser checks focused on the affected interaction, and
report what was actually verified.

## Windows packaging

`scripts/Build-Desktop.ps1` builds and packages the desktop app. The preview build
uses an additional local dataset in `.build-assets/test-laps/`; those recordings
are not included in a source clone. See the README for how to copy this dataset
from an existing preview ZIP before building. Installing from source and using
generated sample laps does not require that dataset.
