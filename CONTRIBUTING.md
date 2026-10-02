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

Run the existing tests after changing application behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

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

## Windows packaging

`scripts/Build-Desktop.ps1` builds and packages the desktop app. The preview build
uses an additional local dataset in `.build-assets/test-laps/`; those recordings
are not included in a source clone. See the README for how to copy this dataset
from an existing preview ZIP before building. Installing from source and using
generated sample laps does not require that dataset.
