# Fresh Python Environment Validation

Author: Dahe Chen. Executed October 1, 2026, 20:20–20:24 UTC.

## Scope and result

The public release at commit
`16bbe7cb3ec5fb520523ae00587ee33041088577` was tested in a newly created
Python virtual environment on the existing Windows workstation. The environment
did not inherit system-site packages. Dependencies were downloaded and installed
from the release's `requirements.txt`; no installed project environment was
reused.

| Check | Observed result |
| --- | --- |
| New virtual environment | Python 3.13.12, Windows AMD64; system-site packages disabled |
| Dependency installation | Exit 0; 43 installed distributions including pip |
| `python -m pip check` | Exit 0; no broken requirements found |
| Public example seeding and `--check-only` | Both exit 0; nine examples verified; existing cases were not overwritten |
| Recorded response replay | All nine outputs matched their saved application decisions and resolved cited IDs |
| Streamlit AppTest | Eighteen case-language views: nine cases in English and Chinese; zero app exceptions |
| Offline smoke safeguards | Zero HTTP requests; zero Gemini API-key reads; zero human reviews written |
| Public evidence integrity | All 27 example JSON files retained their byte hashes |
| Complete public regression suite | **185 passed, 1 skipped in 38.06 seconds**, exit 0 |
| Public clone after testing | Clean tracked working tree; commit unchanged |

The single skip is the explicitly optional comparison with an original private
API attempt. That attempt is absent from the public clone. Portable recording,
hash, citation, tampering, and interface tests ran. The complete suite was run
once because the newly resolved package versions differed from the previously
used environment.

This verifies installation and offline replay on this workstation. It does not
verify a new operating-system installation, another computer, Linux dependency
compatibility, a fresh Docker deployment, new model inference, diagnostic
accuracy, semantic correctness of every explanation, or user benefit. AppTest
checks application behavior, not an observed human usability study.

## Execution and retained failure

The first `py -3.13 -m venv` attempt failed during `ensurepip`: the managed
default execution context could not write a temporary pip wheel under the
Windows system Temp directory. The error was `PermissionError`, not a dependency
resolution failure. Its receipt and output were retained. No application code
or package constraint was changed to make installation pass.

A separate virtual environment was then created with an isolated workspace
`TEMP`/`TMP` directory using authorized execution. Installation began at
20:21:29 UTC and finished at 20:22:40 UTC. The successful installation used:

```powershell
py -3.13 -m venv <new-ignored-workspace-directory>\venv-verified
<venv-python> -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
<venv-python> -m pip check
<venv-python> -m pip freeze --all
<venv-python> -m scripts.seed_official_examples
<venv-python> -m scripts.seed_official_examples --check-only
<venv-python> -m pytest tests -q -p no:cacheprovider --basetemp <fresh-workspace-test-directory>
```

The API-key variable was removed from the child verification process without
reading its value. The one-off nine-case replay/UI audit additionally installed
guards that reject any HTTP request or attempt to read `GEMINI_API_KEY`.
Language switching preserved the selected case and recorded answer. The
human-judgment field and reason stayed empty, and model-sharing consent stayed
unchecked. No fictional reviewer judgment was saved.

The replay audit checked equality with preserved outputs, including the
checkout-priority counterexample; it did not replace a response or score a saved
answer as a new experiment. All 27 public JSON files were hashed before and after
the audit.

## Resolved package inventory

The requirements file permits version ranges, so a later installation may
resolve differently. The following is an observed Windows/Python 3.13 inventory,
not a universal cross-platform lock file. pip itself was supplied by `ensurepip`.

```text
altair==6.3.0
anyio==4.15.1
attrs==26.1.0
certifi==2026.7.22
charset-normalizer==3.5.2
click==8.5.0
colorama==0.4.6
h11==0.16.0
httptools==0.8.0
idna==3.20
iniconfig==2.3.0
itsdangerous==2.2.0
Jinja2==3.1.6
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
MarkupSafe==3.0.3
narwhals==2.26.0
numpy==2.5.3
packaging==26.3
pandas==3.0.6
pillow==12.3.0
pip==25.3
pluggy==1.6.0
protobuf==7.36.2
pyarrow==25.0.1
pydeck==0.9.3
Pygments==2.21.0
pytest==9.1.1
python-dateutil==2.9.0.post0
python-multipart==0.0.32
referencing==0.37.0
requests==2.34.2
rpds-py==2026.6.3
six==1.17.0
starlette==1.7.0
streamlit==1.64.0
toml==0.10.2
typing_extensions==4.16.0
tzdata==2026.4
urllib3==2.8.0
uvicorn==0.54.0
watchdog==6.0.0
websockets==16.1.1
```

## Short Windows reproducer

Run from the public checkout. This creates a distinct environment and temporary
directory under ignored `evaluation/private/`. It clears the API-key variable
only in this PowerShell process; offline replay needs no API key or Docker.

```powershell
$replayRoot = Join-Path (Get-Location).Path ("evaluation\private\replay-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path (Join-Path $replayRoot "tmp") -Force | Out-Null
$env:TEMP = Join-Path $replayRoot "tmp"
$env:TMP = $env:TEMP
$env:GEMINI_API_KEY = $null
py -3.13 -m venv (Join-Path $replayRoot "venv")
$replayPython = Join-Path $replayRoot "venv\Scripts\python.exe"
& $replayPython -m pip install -r requirements.txt
& $replayPython -m pip check
& $replayPython -m scripts.seed_official_examples
& $replayPython -m scripts.seed_official_examples --check-only
& $replayPython -m pytest tests -q -p no:cacheprovider --basetemp (Join-Path $replayRoot "pytest-temp")
& $replayPython -m streamlit run app.py
```

Use **Load recorded analysis** to inspect saved outputs. Calling Gemini is a
separate opt-in action and was not part of this validation. On the managed
workstation, the environment creation and tests required authorized execution
in addition to workspace temporary storage. That permission requirement should
not be confused with an application repair.

## Evidence locations

Local receipts are retained under the ignored directory
`evaluation/private/fresh-env-20261001-f9b050315368491195017de5deff1606/`:

- `setup-receipt.json` and `venv-create.log`: unsuccessful first creation;
  `ensurepip-diagnostic-summary.json` is an explicitly abbreviated summary of
  the separately observed diagnostic traceback.
- `verified-setup-receipt.json`, `venv-create-verified.log`, and `pip-install.log`:
  separate successful creation and dependency installation.
- `python-version.txt`, `pip-version.txt`, `installed-versions.txt`,
  `installed-versions.json`, and `pip-check.txt`: interpreter and package evidence.
- `seed-example-output.txt`, `seed-check-output.txt`, and `smoke-receipt.json`:
  validated example loading.
- `validate_replay_ui.py`, `replay-ui.log`, and `replay-ui-result.json`: guarded
  nine-case replay and eighteen language views.
- `full-pytest.log` and `full-pytest-receipt.json`: complete suite and timestamps.

The tested release's `requirements.txt` SHA-256 was
`88974e998e32b6837f067c617fcfa20e9945bc9102a102a3b76794f21be6afe8`.
The captured `pip freeze --all` file SHA-256 was
`8b30c0e5d252bda272454c657bb284019ffc89042e23d3e838d71dde4301e149`.
These hashes identify the local audited artifacts; they do not substitute for
execution on another platform. The new validation report was not present in the
tested release and is a subsequent documentation addition.
