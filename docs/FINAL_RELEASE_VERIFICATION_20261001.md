# Final Public Release Verification

Author: Dahe Chen. Independently executed October 1, 2026, 20:43–20:46 UTC.

## Verified release

A new clone was fetched from the authorized public
[AutoTriager-Shop repository](https://github.com/chendahe666/AutoTriager-Shop).
It resolved to
[commit `139cfa172b41148412bf2ea677ae4e921dfc3c5c`](https://github.com/chendahe666/AutoTriager-Shop/commit/139cfa172b41148412bf2ea677ae4e921dfc3c5c),
not a copy of the author's existing checkout. The tracked worktree was clean
before and after verification.

| Check | Observed result |
| --- | --- |
| Public example data | All 27 JSON files across nine examples matched the author's files byte for byte |
| Final Challenge 2 PDF | Expected SHA-256 and author-file bytes matched |
| Final Enhancement PPTX | Expected SHA-256 and author-file bytes matched |
| Frozen scientific code | All five Gemini function hashes, schema bytes, and scorer bytes matched `research/selected_method.json` |
| Requirements | Byte-identical to the verified requirement file |
| Retired native-only PDF | Absent from the new clone's filesystem and current tracked tree |
| Dependency check | `pip check` exit 0; no broken requirements found |
| Example loading | Seeding and `--check-only` both exit 0; nine public examples verified |
| Complete public regression | **199 passed, 1 skipped in 38.97 seconds**, exit 0 |
| Private-source boundary | Original private API attempts absent; no actual human-review directory created |

The only skipped test was
`tests/test_recorded_analysis.py:112`: the optional comparison with an original
private API attempt, intentionally excluded from public clones. Public replay,
integrity checks, the new component helper, and interface regressions ran in the
complete suite. The count is separate from the author's 200-test local run,
which had that private source available.

## Artifact identity

| Published artifact | Verified SHA-256 |
| --- | --- |
| `output/pdf/AutoTriager_Challenge2_OfficialShop_Dahe_Chen_Final.pdf` | `4ae20f18da1280086fb4ab008da3644737c8e0cbb5f790def6309f1974f90a51` |
| `output/slides/AutoTriager_OfficialShop_Checkpoint_Dahe_Chen_Final.pptx` | `2da624831ff9d4c67fba5cff43657a0a26b07804174eca4c04b3a5e4b3756eb2` |
| `requirements.txt` | `88974e998e32b6837f067c617fcfa20e9945bc9102a102a3b76794f21be6afe8` |

This release check confirms that published artifacts match the separately
rendered and reviewed final files. It does not claim a new native PowerPoint
inspection or regeneration of the PDF in this verification environment.
The PPTX is an eight-slide Enhancement checkpoint, not a full Talk (4) roadmap.

## Execution environment and commands

The check reused the isolated Python 3.13.12 virtual environment created for
the earlier [fresh dependency validation](FRESH_ENVIRONMENT_VALIDATION_20261001.md)
on this same Windows host. System-site packages remained disabled, and the
requirements file was unchanged. No new dependency installation was needed
for this release check. This combines a newly fetched public source tree with
an already verified isolated environment; it does not constitute another-machine
or new-operating-system validation.

```text
git clone --no-hardlinks https://github.com/chendahe666/AutoTriager-Shop.git <fresh-ignored-checkout>
git -C <fresh-ignored-checkout> rev-parse HEAD
<verified-venv-python> -m pip check
<verified-venv-python> -m scripts.seed_official_examples
<verified-venv-python> -m scripts.seed_official_examples --check-only
<verified-venv-python> -m pytest tests -q -rs -p no:cacheprovider --basetemp <fresh-workspace-temp>
```

The complete suite ran once, using an authorized execution context and fresh
workspace `TEMP`/`TMP` and pytest storage because earlier setup permission errors
had already been established and retained. No permission failure occurred in
this release attempt. The configured Gemini key was removed from the child
process without reading its value. No live Gemini, Shop capture, fault
intervention, Docker operation, or human judgment was performed.

The initial byte/frozen-code audit completed at 20:44:18 UTC. The execution
batch ran from 20:44:48 to 20:45:35 UTC. A separate post-test audit at 20:46:09 UTC
confirmed unchanged artifact/data bytes, frozen hashes, clean tracked source,
and continued absence of the retired PDF and private original attempts.

## Evidence records and limits

The new clone and immutable local verification receipts are under ignored
`evaluation/private/final-release-20261001-dbc7428a0088490fbeba438f95d53720/`:

- `clone.log` and `clone-receipt.json`: the actual remote clone operation.
- `verify_release.py`, `byte-and-frozen-verification.json`, and its log:
  initial commit, public bytes, frozen hashes, and retirement checks.
- `pip-check.log`, `seed.log`, `seed-check.log`, `pytest.log`, and
  `execution-receipt.json`: software execution and the explicit skip reason.
- `post-test-byte-and-frozen-verification.json` and its log: independent
  post-execution integrity check, without overwriting the initial receipt.

Publication and software reproducibility are verified for the stated release
and host. The thirty-call study's findings are unchanged; no diagnostic
improvement, optimal action, human benefit, grade, or conference acceptance
follows from this check. Meaningful student review, historical design/feedback
confirmation, and course submission remain separate activities. Removal from
the current Git tree does not erase old Git history or prove deletion of the
separate old CoDesign repository.

This verification note is a subsequent documentation addition and was not part
of the tested `139cfa1` commit. Publishing it must preserve that distinction.
