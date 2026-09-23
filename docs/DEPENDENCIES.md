# Dependency pinning policy

LittleNet's AI/safety stacks pin **exact versions** everywhere they matter so a
fresh environment resolves to the same tested binaries every time.

## Pin surfaces

| Surface                  | File(s)                                             |
|--------------------------|-----------------------------------------------------|
| Text pipeline            | `requirements-text.txt`                             |
| Image pipeline           | `requirements-ai.txt` (includes `-r requirements-text.txt`) |
| Safety/PII pipeline      | `requirements-safety.txt`                           |
| Core/backend + rapidocr  | `requirements-core.txt`                             |
| Modal AI image           | `modal_ai.py` (`modal.Image.pip_install(...)` list) |

`modal_ai.py` must mirror the exact pins in the matching `requirements-*.txt`
files. A contract test (`tests/test_dependency_pins.py`) enforces this: any
drift between the requirements files and `modal_ai.py` fails CI.

## Known collision

- `nudenet` transitively requires `opencv-python-headless`.
- Modal's image intentionally installs non-headless `opencv-python`
  (`libgl1` is apt-installed for `rapidocr-onnxruntime`, which declares
  `opencv-python`, not headless). One `cv2` provider avoids a
  site-packages collision between the two distributions.

## Updating a pin

1. Change the exact pin in the matching `requirements-*.txt`.
2. Mirror the same exact pin in `modal_ai.py`.
3. Run the contract test: `pytest tests/test_dependency_pins.py`.
4. Verify the pinned version installs (`pip install <pkg>==<ver>`, or a
   resolver dry-run) and, for ML packages, that the trained-model loaders
   still pass their suite (`pytest tests/test_safety_*`).
5. Note the change and the verification date in the changelog below.

## Changelog

| Date       | Change                                                                 |
|------------|------------------------------------------------------------------------|
| 2026-09-23 | transformers bumped 5.0.0 -> 5.10.0 (minimum version fixing pip-audit PYSEC-2026-2289/2290/3929). Trained text checkpoint re-verified under 5.10.0: loads clean, bullying text -> 0.998, all 13 labels sane. |
| 2026-09-22 | Exact pins locked: torch 2.13.0, torchvision 0.28.0, transformers 5.0.0, nudenet 3.4.2, ultralytics 8.4.159, scenedetect-headless 0.7.1, presidio-analyzer 2.2.364, spacy 3.8.16, opencv-python-headless 4.11.0.86. Full transitive resolver dry-run completed successfully in the sandbox (every pinned distribution resolved, `Would install` set produced); no disk-limit blocker. Python 3.11/Modal runtime resolution still needs validation at deploy time. |
