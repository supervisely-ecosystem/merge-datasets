"""Runs the merge against a real instance for every case in cases/.

Opt-in: SLY_CONTRACT_TESTS=1, credentials in ~/supervisely.env (SERVER_ADDRESS, API_TOKEN),
SLY_CONTRACT_PROJECT_ID (images or videos project, only read) and SLY_CONTRACT_WORKSPACE_ID (a dedicated test
workspace: every case creates one new project there; nothing is deleted).

    SLY_CONTRACT_TESTS=1 SLY_CONTRACT_PROJECT_ID=123 SLY_CONTRACT_WORKSPACE_ID=45 pytest -m contract tests/contract
"""

import glob
import json
import os
from collections import Counter

import pytest
import supervisely as sly
from dotenv import dotenv_values, load_dotenv

from src import platform_io
from src.core.datasets import with_nested
from src.core.names import NameConflict
from src.core.options import Destination
from src.merger import merge_datasets

CASES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "cases", "*.env")))

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(os.getenv("SLY_CONTRACT_TESTS") != "1", reason="contract tests are opt-in"),
]


@pytest.fixture(scope="module")
def api():
    load_dotenv(os.path.expanduser("~/supervisely.env"))
    return sly.Api.from_env()


def items(api, project_type, dataset_id):
    """[(name, hash, annotation summary)] of a dataset."""
    if project_type == "videos":
        videos = api.video.get_list(dataset_id)
        anns = api.video.annotation.download_bulk(dataset_id, [v.id for v in videos]) if videos else []
        by_id = {a["videoId"]: a for a in anns}
        return [
            (v.name, v.hash, (len(by_id[v.id]["objects"]), sum(len(f["figures"]) for f in by_id[v.id]["frames"])))
            for v in videos
        ]
    images = api.image.get_list(dataset_id)
    anns = {a.image_id: a.annotation for a in api.annotation.download_batch(dataset_id, [i.id for i in images])}
    summary = {
        i.id: json.dumps(sorted((o["classTitle"], o["geometryType"]) for o in anns[i.id]["objects"])) for i in images
    }
    return [(i.name, i.hash, summary[i.id]) for i in images]


@pytest.mark.parametrize("case", CASES, ids=os.path.basename)
def test_case_merges_into_one_dataset(case, api):
    project_id = int(os.environ["SLY_CONTRACT_PROJECT_ID"])
    workspace_id = int(os.environ["SLY_CONTRACT_WORKSPACE_ID"])
    values = dotenv_values(case)
    mode = NameConflict(values["NAME_CONFLICT"])
    project, meta = platform_io.get_project(api, project_id)
    all_datasets = platform_io.list_datasets(api, project_id)
    roots = [ds for ds in all_datasets if ds.parent_id is None]
    wanted = roots if values["DATASETS"] == "*" else [ds for ds in roots if ds.name in values["DATASETS"].split(",")]
    datasets = with_nested(all_datasets, [ds.id for ds in wanted])
    source_before = {ds.id: items(api, project.type, ds.id) for ds in datasets}

    result = merge_datasets(
        api, project, meta, datasets, Destination(project_name=f"contract {os.path.basename(case)}"), mode, workspace_id
    )

    assert result.project.workspace_id == workspace_id and result.project.type == project.type
    assert platform_io.get_meta(api, result.project.id) == meta
    merged = items(api, project.type, result.dataset.id)
    names = [name for name, _, _ in merged]
    assert len(names) == len(set(names))
    total = sum(len(rows) for rows in source_before.values())
    assert result.items_merged + result.items_ignored == total
    assert len(merged) == result.items_merged
    sources = Counter((h, ann) for rows in source_before.values() for _, h, ann in rows)
    copies = Counter((h, ann) for _, h, ann in merged)
    assert not copies - sources, "every merged item is a copy of a source item with its annotation"
    if mode is NameConflict.IGNORE:
        assert set(names) == {name for rows in source_before.values() for name, _, _ in rows}
    else:
        assert result.items_ignored == 0 and copies == sources
    if mode is NameConflict.DATASET_PREFIX:
        first = {}
        for ds in datasets:
            for name, _, _ in source_before[ds.id]:
                first.setdefault(name, ds.name)
        for name in names:
            assert name in first or any(name.startswith(f"{ds.name}_") for ds in datasets), name
    assert {ds.id: items(api, project.type, ds.id) for ds in datasets} == source_before, "the source must not change"
