# merge-datasets

GUI app: images or videos project → the items of the selected datasets (with their nested datasets) copied into
one dataset of a new or an existing project. `MODERNIZE.md` has the behaviour contract and the intentional changes
versus the pre-2026 (AppService + `gui_template`) version.

- Entry: `uvicorn src.main:app` (`config.json` `entrypoint`); modules import each other as `src.*`.
  `src/main.py` is the composition root (env → Api → GUI); creating `app` at import is required by uvicorn.
- `src/ui.py` (`MergeGui`): widgets, mode switches and the Merge handler; everything platform-side comes in
  through `Actions` (callbacks wired in `main.py`). The session stays open after a merge (old behaviour).
- `src/merger.py`: destination (create / open, meta merge → `MetaConflict`) and the copy in batches of 50;
  `src/platform_io.py` is the only module calling the API; `src/core/` is pure (name conflicts, dataset tree,
  GUI choice validation).
- Items are added by id (images `upload_ids`, videos `upload_ids` by hash/link); image annotations are copied
  as JSON (`upload_jsons`, `skip_bounds_validation`), video annotations rebuilt with the destination meta.

Runtime: bare `supervisely/base-py-sdk-hardened:<sdk>` (Python 3.14), no per-app image because
`dev_requirements.txt` holds only the SDK. SDK must stay within the range `supervisely/versions.json`
allows for `instance_version` (6.17.22 → [6.74.29, 6.74.35)).

Keep: `config.json` `name`/`context_menu`, the `nameConflicts` values `ignore`/`rename`/`dsrename`, the defaults
`my_Project`/`my_dataset`, the dialog texts, and that the source datasets are only read.

Gotchas: `TreeSelect` (non-flat) may return only a parent when all its children are checked; `with_nested`
expands the selection, so never rely on the widget value alone. `ProjectThumbnail` crashes on a project without
items (`_thumbnail_info` guards it). The destination dataset is skipped as a source.

Tests: `pytest` (unit, offline; includes the GUI through `Application.test_client` and the merge against a fake
API) · `SLY_CONTRACT_TESTS=1 SLY_CONTRACT_PROJECT_ID=<id> SLY_CONTRACT_WORKSPACE_ID=<test ws> pytest -m contract tests/contract`
(creates one project per `cases/*.env` in the test workspace, deletes nothing).
