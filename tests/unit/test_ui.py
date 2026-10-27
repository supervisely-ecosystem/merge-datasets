"""The GUI in-process through Application.test_client: rendering, mode switches and the Merge handler."""

import asyncio

import pytest
import supervisely as sly
from supervisely.app import DataJson, StateJson
from supervisely.app.singleton import Singleton

from src.core.names import NameConflict
from src.core.options import Destination
from src.merger import MergeResult, MetaConflict
from src.ui import Actions, MergeGui


def info(cls, **values):
    return cls(**{**{f: None for f in cls._fields}, **values})


PROJECT = info(sly.ProjectInfo, id=10, name="fruits", workspace_id=5, type="images", reference_image_url=None)
OTHER = info(sly.ProjectInfo, id=20, name="target", workspace_id=5, type="images")
DATASETS = [
    info(sly.DatasetInfo, id=1, name="train", parent_id=None, items_count=2),
    info(sly.DatasetInfo, id=2, name="hard", parent_id=1, items_count=1),
    info(sly.DatasetInfo, id=3, name="val", parent_id=None, items_count=4),
]
TARGET_DATASETS = [info(sly.DatasetInfo, id=200, name="merged", parent_id=None, items_count=1)]
NEW_PROJECT = info(sly.ProjectInfo, id=30, name="my_Project", workspace_id=5, type="images")
NEW_DATASET = info(sly.DatasetInfo, id=300, name="my_dataset", parent_id=None)


@pytest.fixture(autouse=True)
def fresh_app(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    Singleton._instances.clear()
    yield
    Singleton._instances.clear()


class Recorder:
    def __init__(self, fail=None):
        self.merges, self.merged, self.listed = [], [], []
        self.projects = [OTHER, PROJECT]
        self.fail = fail

    def list_datasets(self, project_id):
        self.listed.append(project_id)
        return {10: DATASETS, 20: TARGET_DATASETS}[project_id]

    def merge(self, options, datasets, progress):
        self.merges.append((options, [ds.id for ds in datasets]))
        if self.fail:
            raise self.fail
        progress(3)
        self.projects = [*self.projects, NEW_PROJECT]
        return MergeResult(NEW_PROJECT, NEW_DATASET, len(datasets), 3, 0)

    def actions(self):
        return Actions(
            list_source_datasets=lambda: DATASETS,
            list_projects=lambda: self.projects,
            list_datasets=self.list_datasets,
            merge=self.merge,
            merged=self.merged.append,
        )


def make(recorder):
    gui = MergeGui(PROJECT, recorder.actions())
    return gui, sly.Application(layout=gui.layout)


def post(app, route, values):
    state = dict(StateJson())
    for widget, value in values.items():
        state[widget.widget_id] = {**state[widget.widget_id], "value": value}
    response = asyncio.run(app.test_client.post(route, json={"state": state, "context": {}}))
    assert response.status_code == 200, response.text
    return response


def click(app, gui, values):
    return post(app, f"/{gui.merge_button.widget_id}/button_clicked_cb", values)


def items(*pairs):
    return [{"id": i, "label": name} for i, name in pairs]


def test_page_renders_with_the_old_defaults():
    gui, app = make(Recorder())

    response = asyncio.run(app.test_client.get("/"))

    assert response.status_code == 200
    tree = DataJson()[gui.datasets.widget_id]["items"]
    assert [(d["id"], d["label"]) for d in tree] == [(1, "train"), (3, "val")]
    assert tree[0]["children"] == [{"id": 2, "label": "hard"}]
    assert gui.name_conflict.get_value() == NameConflict.RENAME
    assert gui.project_mode.get_value() == "newProject"
    assert gui.project_name.get_value() == "my_Project"
    assert gui.dataset_name.get_value() == "my_dataset"
    assert [i.value for i in gui.dst_project.get_items()] == [20, 10]
    assert gui.dst_project.get_value() == PROJECT.id  # the source project is preselected
    assert DataJson()[gui.dataset_mode.widget_id]["hide"] is True


def test_merge_without_datasets_shows_the_reason_and_does_nothing():
    recorder = Recorder()
    gui, app = make(recorder)

    click(app, gui, {})

    assert recorder.merges == []
    assert DataJson()[gui.error.widget_id]["text"] == "Please, select at least one dataset to merge"
    assert DataJson()[gui.error.widget_id]["hide"] is False


def test_merge_into_a_new_project_takes_nested_datasets_and_reports():
    recorder = Recorder()
    gui, app = make(recorder)

    click(app, gui, {gui.datasets: items((1, "train")), gui.name_conflict: "ignore"})

    ((options, dataset_ids),) = recorder.merges
    assert dataset_ids == [1, 2]
    assert options.destination == Destination(None, "my_Project", None, "my_dataset")
    assert options.name_conflict is NameConflict.IGNORE
    assert [r.project for r in recorder.merged] == [NEW_PROJECT]
    assert StateJson()["slyAppShowDialog"] is True
    assert DataJson()["slyAppDialogMessage"] == (
        "2 datasets from project 'fruits' have been successfully merged to the dataset: 'my_dataset' "
        "in project 'my_Project'."
    )
    # the session stays open: controls unlocked, the new project is offered as a destination
    assert DataJson()[gui.merge_button.widget_id]["disabled"] is False
    assert DataJson()[gui.merge_button.widget_id]["loading"] is False
    assert [i.value for i in gui.dst_project.get_items()] == [20, 10, 30]


def test_existing_project_mode_shows_its_datasets_and_merges_into_one():
    recorder = Recorder()
    gui, app = make(recorder)

    post(app, f"/{gui.dst_project.widget_id}/value_changed", {gui.dst_project: 20})
    post(app, f"/{gui.project_mode.widget_id}/value_changed", {gui.project_mode: "existingProject"})
    assert DataJson()[gui.dataset_mode.widget_id]["hide"] is False
    assert DataJson()[gui.dst_dataset.widget_id]["items"] == [{"id": 200, "label": "merged"}]

    click(
        app,
        gui,
        {
            gui.datasets: items((3, "val")),
            gui.project_mode: "existingProject",
            gui.dst_project: 20,
            gui.dataset_mode: "existingDataset",
            gui.dst_dataset: {"id": 200, "label": "merged"},
        },
    )

    ((options, dataset_ids),) = recorder.merges
    assert dataset_ids == [3]
    assert options.destination == Destination(20, "my_Project", 200, "my_dataset")


def test_existing_dataset_mode_without_a_dataset_is_rejected():
    recorder = Recorder()
    gui, app = make(recorder)

    click(
        app,
        gui,
        {
            gui.datasets: items((3, "val")),
            gui.project_mode: "existingProject",
            gui.dst_project: 20,
            gui.dataset_mode: "existingDataset",
        },
    )

    assert recorder.merges == []
    assert DataJson()[gui.error.widget_id]["text"] == "Please, select one of the existing Datasets"


def test_back_to_new_project_resets_the_dataset_mode():
    gui, app = make(Recorder())
    post(app, f"/{gui.project_mode.widget_id}/value_changed", {gui.project_mode: "existingProject"})

    route = f"/{gui.project_mode.widget_id}/value_changed"
    post(app, route, {gui.project_mode: "newProject", gui.dataset_mode: "existingDataset"})

    assert gui.dataset_mode.get_value() == "newDataset"
    assert DataJson()[gui.dataset_mode.widget_id]["hide"] is True


def test_meta_conflict_shows_the_old_error_and_unlocks():
    recorder = Recorder(fail=MetaConflict("kiwi"))
    gui, app = make(recorder)

    click(app, gui, {gui.datasets: items((3, "val")), gui.project_mode: "existingProject", gui.dst_project: 20})

    assert recorder.merged == []
    assert DataJson()["slyAppDialogStatus"] == "error"
    assert DataJson()["slyAppDialogMessage"].startswith("Error during merge, source project meta has conflics")
    assert DataJson()[gui.merge_button.widget_id]["loading"] is False
    assert DataJson()[gui.datasets.widget_id]["disabled"] is False


def test_unexpected_failure_unlocks_the_controls_and_propagates():
    recorder = Recorder(fail=RuntimeError("boom"))
    gui, app = make(recorder)

    state = dict(StateJson())
    state[gui.datasets.widget_id] = {**state[gui.datasets.widget_id], "value": items((3, "val"))}
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            app.test_client.post(
                f"/{gui.merge_button.widget_id}/button_clicked_cb", json={"state": state, "context": {}}
            )
        )
    assert recorder.merged == []
    assert DataJson()[gui.merge_button.widget_id]["loading"] is False
