# Modernization notes: merge-datasets

Rewrite of `merge-datasets` to the `sly-app-standard` (local, not released). Base: `origin/master` @ 458f66c
(v1.2.4). Branch `local/modernize`, nothing committed. Fresh clone at `workapps/merge-datasets` (was mirror-only).

## Behaviour contract (kept)

**Entry point.** Context menu of an images or videos project (`images_project`, `videos_project`), GUI session in
`workspace_tasks`. No modal options; the project arrives as `modal.state.slyProjectId`. Other project types are
rejected at startup.

**GUI** (same three cards and texts). 1. Input Project (thumbnail). 2. Datasets to merge. 3. Merge Settings:
- "How to solve name conflicts?": `ignore` / `rename` (default) / `dsrename`, same labels and examples;
- "Destination Project": Create new Project (name, default `my_Project`) or Add to existing Project (projects of
  the same type in the workspace);
- "Destination Dataset": Create new Dataset (name, default `my_dataset`) or, for an existing project only,
  Add to existing dataset; switching back to a new project resets it to a new dataset;
- "Merge Datasets" button; the same red messages for an incomplete choice ("Please, define the name of a new
  Project", "Please, select one of the existing Projects", "... new Dataset", "... existing Datasets").

**Output.**
- New project: in the source project's workspace, source type, source meta, name as typed (`_001`, ... when
  taken); dataset as typed.
- Existing project: its meta is merged with the source meta first; on a conflict (class with another shape, tag
  with another value type) the old error dialog ("Error during merge, source project meta has conflics ...") and
  nothing is created. New dataset gets a free name (`_001`) when taken.
- Items: images by id (`upload_ids`, no pixel re-upload, image meta as before) + annotation JSON as is
  (`upload_jsons`, `skip_bounds_validation=True`); videos by hash/link + annotation rebuilt with the destination meta.
- Name conflicts against the destination dataset and the items already merged in this run:
  `ignore` skips; `rename` → `name_01.ext`, `_02`, ...; `dsrename` → `<dataset>_<name>`.
- Dialog "N datasets from project 'X' have been successfully merged to the dataset: 'D' in project 'P'." +
  " Items ignored: K" when K > 0.
- Workflow: source project as input at each merge, destination project as output after it.
- The session stays open after a merge (README "Stop application manually"); the user can merge again.
- Source datasets are only read.

## Intentional changes

1. **Nested datasets.** The old list showed only top-level datasets (`dataset.get_list` without `recursive`); a
   selected parent merged only its own items and nested items were silently dropped (on #1317 every top-level
   dataset is empty, so the old app merged 0 of 22 images). Now the list is the dataset tree, checking a dataset
   includes its nested datasets, and their items go to the same flat destination dataset. The existing-dataset
   picker lists nested datasets too.
2. **Videos + "Add dataset name" crashed** on the first conflict (`video_info.name = ...` on a NamedTuple →
   `AttributeError: can't set attribute`), leaving a partial project. Now works (verified on dev, V3).
3. **Images + "Add dataset name" did not re-check the prefixed name**; when `<dataset>_<name>` was taken too, the
   upload failed. Now it gets a numeric suffix (what the old video branch did).
4. **The destination dataset is never a source.** Old: choosing an existing dataset that was also selected copied
   its own items into itself (duplicates with `rename`) and could re-copy items merged into it earlier in the run.
   Now it is skipped; the dialog counts only the datasets actually merged.
5. **Progress** counts the items of the selected datasets (old: all project items, so the bar rarely reached 100 %;
   ignored images were counted twice).
6. **Task output** is set to the destination project after each merge (old: none).
7. **New UI on `sly.Application` widgets** instead of the `gui_template` page: dataset tree dropdown instead of
   the file-viewer table (no item-count column); the button is always enabled and an incomplete choice shows the
   old message under it after the click; the existing project is a dropdown with the source project preselected
   (old picker started empty); after a merge the lists are refreshed so a new project/dataset can be the next
   destination; the meta-conflict dialog no longer clears the chosen destination dataset.
8. **Datasets are merged in project tree order**, not in click order (decides which item keeps its original name
   on a conflict).
9. Names typed for a new project/dataset are trimmed; whitespace-only names count as empty.
10. **Runs on the hardened image (Python 3.14)**. Videos are added in batches with `api.video.upload_ids` (same
    hash/link mechanism as the old per-video `add_existing`; link videos are uploaded with `skip_download=True`,
    not exercised: no link videos on dev).

## Dropped

- `AppService` runtime, `src/gui.html`, `src/merge_datasets.py` (module-level env reads, globals), `src/ui.py`
  (task-field progress helpers), `src/workflow.py` → `src/platform_io.py` (same lineage calls).
- `debug.env` (token placeholders, another app's paths), old `local.env` (ids of another instance),
  `.vscode/` (launch config for the old script) → `local.env` + `~/supervisely.env`.
- No tests existed before.

## Versions, image, CI

- **Image: `supervisely/base-py-sdk-hardened:6.74.34`** (was the shared `supervisely/base-py-sdk:6.74.34`).
  No deps beyond the SDK, so no per-app image. Tag checked on Docker Hub (200).
- **SDK stays at 6.74.34** with `instance_version` 6.17.22 (CI range [6.74.29, 6.74.35)). A newer SDK needs a
  higher `instance_version` — a product decision, not taken.
- `config.json`: `version: "2.0.0"`, uvicorn `entrypoint` + `port`; `main_script`/`gui_template` removed;
  `name`, `context_menu`, categories, icon, poster unchanged.
- CI: this repo has no `build-image` job (`release.yml` only calls `workflows/common.yml`), so the open question
  about per-app image builds for bare-hardened apps does not apply here. Workflows left unchanged.
- README screenshots show the old UI; not retaken.

## Verification (2026-10-25, dev.internal.supervisely.com)

- **Unit tests** 49/49 in a macOS venv (Python 3.14.3) and 49/49 inside `base-py-sdk-hardened:6.74.34`
  (Python 3.14.7, amd64). `ruff check` and `ruff format --check` clean (`target-version = py314`).
  Covers name resolution (`free_name` equals the SDK's `generate_free_name` on 2000 random cases), dataset tree,
  choice validation, the merge against a fake API for images and videos (all modes, new/existing destination,
  meta conflict creates nothing, destination-as-source, batches of 50) and the GUI via `Application.test_client`.
- **Equivalence, generated data** (`.modernize/equiv_generated.py`): the OLD `merge_projects` callback (from
  `origin/HEAD`, AppService stubbed) vs new on 1500 random flat images/videos projects with heavy name collisions,
  every mode, new / existing project + new / existing dataset, source project as destination. 904 identical
  destinations, 176 identical meta-conflict refusals; every other case is an intentional change: 215 old crashes
  on `dsrename` (changes 2, 3), 205 destination-dataset-is-a-source cases (change 4). 0 unexplained differences.
- **Equivalence, dev projects** (`.modernize/equiv_dev.py`, results in `.modernize/equiv_dev_results.jsonl`): old
  callback and new merge on the same datasets, outputs in ws 733, compared by item name, file hash, annotation
  (objects, geometry, tags), image meta, and destination meta:
  I1 #46, I2 #26, I3 #27, I4 #1317, I5 #9390, I6-I8 sandbox images source (three datasets with the same names,
  rename/ignore/dsrename), I9 existing project + existing dataset, I10 existing project + new dataset (ignore),
  V1/V2 videos (rename/ignore), V4 videos into an existing dataset: **all identical**, same dialog texts.
  I11 meta conflict: both refuse with the same message, conflict project untouched. V3 videos dsrename: old crashes
  (change 2), new gives `ds1_<name>` with full annotations (11 objects / 543 figures as in the source).
  Nested (change 1) through the GUI path: #1317 22 images (old 0), #9390 2 (old 1), sandbox images 15 (old 13),
  sandbox videos 5 (old 4).
- **Contract tests** (`cases/*.env`): 3/3 on the sandbox images source #9458, 3/3 on the sandbox videos source #9464.
- **In the real image, production mode:** `uvicorn src.main:app` in `base-py-sdk-hardened:6.74.34`, `ENV=production`,
  debug task 62726 (port 8014), driven over HTTP like the browser (`.modernize/drive.py`): empty click → "Please,
  select at least one dataset to merge"; merge 1 (ds1 + ds3 with nested inner, dsrename) → project #9546 with
  10 images (`ds3_*`, `inner_*` prefixes, labels kept); merge 2 in the same session (existing project #9462,
  existing dataset, ignore) → "Items ignored: 5"; controls unlocked after each run; task output set to the last
  destination; workflow shows input #9458 and outputs #9546, #9462; logs without warnings or errors (only the known
  `--ws websockets` deprecation).
- Not verified: the page in a real browser on the platform (tree-select parent/child value shape is handled by
  expanding in code either way), link-based videos, very large datasets, a failure in the middle of a merge.

## Objects created on dev (team 1, ws 733; nothing deleted)

Inputs: 9458 `merge-ds src images`, 9464 `merge-ds src videos`, 9461/9462 `merge-ds dst images (old/new)`,
9463 `merge-ds dst conflict`, 9466/9467 `merge-ds dst videos (old/new)`.
Comparison outputs: 9475-9531 `merge-ds eq <scenario> old|new|new-nested` (incl. `_001` repeats of I4/I5/V1 from an
aborted first run; 9530 is the partial project of the old V3 crash). Production run: 9546 `merge-ds prod run`
(merge 2 added to 9462). Contract: 9551, 9553, 9555 (images), 9557-9559 (videos) `contract <case>.env`.
Debug task 62726 (shared "Develop and Debug" session, port 8014). 9562 `merge-ds src videos(images)` is not mine.

## Questions for the user

1. Keep the session open after a merge (as now, matches the old README) or close it like convert-class-shape?
2. Raise `instance_version` to allow a newer SDK? (not done)
3. Retake README screenshots for the new UI?
