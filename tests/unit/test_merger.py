"""merge_datasets end to end against an in-memory stand-in for the few API calls it makes."""

import itertools
from types import SimpleNamespace as NS

import pytest
import supervisely as sly
from supervisely.api.video.video_api import VideoInfo

from src.core.datasets import with_nested
from src.core.names import NameConflict
from src.core.options import Destination
from src.merger import MergeResult, MetaConflict, merge_datasets

LEMON = sly.ObjClass("lemon", sly.Rectangle)
KIWI_BITMAP = sly.ObjClass("kiwi", sly.Bitmap)
KIWI_POLYGON = sly.ObjClass("kiwi", sly.Polygon)
META = sly.ProjectMeta(obj_classes=[LEMON, KIWI_BITMAP])


def info(cls, **values):
    return cls(**{**{f: None for f in cls._fields}, **values})


class FakeApi:
    """Source project 10 (workspace 5): "train" (a, b) > nested "hard" (a); "val" (a, c); "empty".

    Project 20 in the same workspace holds dataset 200 "merged" with an item named "a.jpg".
    """

    def __init__(self, project_type="images", dst_meta=None):
        self._ids = itertools.count(1000)
        self.type = project_type
        ext = ".jpg" if project_type == "images" else ".mp4"
        self.ext = ext
        self.source = info(sly.ProjectInfo, id=10, name="fruits", workspace_id=5, type=project_type)
        self.projects = {
            10: self.source,
            20: info(sly.ProjectInfo, id=20, name="target", workspace_id=5, type=project_type),
        }
        self.metas = {10: META.to_json(), 20: (dst_meta or sly.ProjectMeta()).to_json()}
        self.datasets = {
            1: info(sly.DatasetInfo, id=1, name="train", parent_id=None, project_id=10, items_count=2),
            2: info(sly.DatasetInfo, id=2, name="hard", parent_id=1, project_id=10, items_count=1),
            3: info(sly.DatasetInfo, id=3, name="val", parent_id=None, project_id=10, items_count=2),
            4: info(sly.DatasetInfo, id=4, name="empty", parent_id=None, project_id=10, items_count=0),
            200: info(sly.DatasetInfo, id=200, name="merged", parent_id=None, project_id=20, items_count=1),
        }
        self.items = {
            1: [self._item(11, "a"), self._item(12, "b")],
            2: [self._item(21, "a")],
            3: [self._item(31, "a"), self._item(32, "c")],
            4: [],
            200: [self._item(201, "a")],
        }
        self.anns = {item.id: self._ann(item.id) for items in self.items.values() for item in items}
        self.copied = []  # (dst dataset id, new name, source item id)
        self.uploaded_anns = {}  # new item id -> annotation (json or VideoAnnotation)
        self.created = []

        self.project = NS(
            get_info_by_id=lambda pid, raise_error=False: self.projects[pid],
            get_meta=lambda pid: self.metas[pid],
            update_meta=self.metas.__setitem__,
            create=self._create_project,
        )
        self.dataset = NS(get_info_by_id=lambda did, raise_error=False: self.datasets[did], create=self._create_dataset)
        self.image = NS(get_list=self._list, upload_ids=self._upload_image_ids)
        self.annotation = NS(download_batch=self._download_batch, upload_jsons=self._upload_jsons)
        self.video = NS(
            get_list=self._list,
            upload_ids=self._upload_video_ids,
            annotation=NS(download_bulk=self._download_bulk, append=self.uploaded_anns.__setitem__),
        )

    def _item(self, item_id, stem):
        if self.type == "images":
            return info(sly.ImageInfo, id=item_id, name=stem + self.ext, width=8, height=6)
        return info(VideoInfo, id=item_id, name=stem + self.ext, hash=f"h{item_id}", frames_count=3)

    def _ann(self, item_id):
        if self.type == "images":
            ann = sly.Annotation((6, 8), labels=[sly.Label(sly.Rectangle(1, 1, 3, item_id % 5 + 3), LEMON)])
            return ann.to_json()
        obj = sly.VideoObject(LEMON)
        figure = sly.VideoFigure(obj, sly.Rectangle(1, 1, 3, 4), frame_index=item_id % 3)
        ann = sly.VideoAnnotation(
            (6, 8),
            3,
            objects=sly.VideoObjectCollection([obj]),
            frames=sly.FrameCollection([sly.Frame(item_id % 3, [figure])]),
        )
        return {**ann.to_json(), "videoId": item_id}

    def _list(self, dataset_id):
        return list(self.items[dataset_id])

    def _create_project(self, workspace_id, name, type, change_name_if_conflict):
        assert change_name_if_conflict is True
        project = info(sly.ProjectInfo, id=next(self._ids), name=name, workspace_id=workspace_id, type=type)
        self.projects[project.id] = project
        self.created.append(project)
        return project

    def _create_dataset(self, project_id, name, change_name_if_conflict):
        assert change_name_if_conflict is True
        dataset = info(sly.DatasetInfo, id=next(self._ids), name=name, project_id=project_id, items_count=0)
        self.datasets[dataset.id] = dataset
        self.items[dataset.id] = []
        self.created.append(dataset)
        return dataset

    def _add(self, dataset_id, names, ids):
        assert len(set(names)) == len(names)
        taken = {i.name for i in self.items[dataset_id]}
        assert not taken & set(names), "the server rejects taken names"
        new = []
        for name, src_id in zip(names, ids, strict=True):
            item = self._item(next(self._ids), "x")._replace(name=name)
            self.items[dataset_id].append(item)
            self.copied.append((dataset_id, name, src_id))
            new.append(item)
        return new

    def _upload_image_ids(self, dataset_id, names, ids):
        return self._add(dataset_id, names, ids)

    def _upload_video_ids(self, dataset_id, names, ids, infos):
        assert [i.id for i in infos] == ids
        return self._add(dataset_id, names, ids)

    def _download_batch(self, dataset_id, ids):
        assert {i.id for i in self.items[dataset_id]} >= set(ids)
        return [NS(image_id=i, annotation=self.anns[i]) for i in reversed(ids)]  # order must not matter

    def _download_bulk(self, dataset_id, ids):
        assert {i.id for i in self.items[dataset_id]} >= set(ids)
        return [self.anns[i] for i in reversed(ids)]

    def _upload_jsons(self, ids, anns, skip_bounds_validation):
        assert skip_bounds_validation is True
        self.uploaded_anns.update(zip(ids, anns, strict=True))

    def source_datasets(self, *ids):
        listed = [ds for ds in self.datasets.values() if ds.project_id == 10]
        return with_nested(listed, ids)

    def copied_from(self, dataset_id):
        """{new name: source item id} in a destination dataset."""
        return {name: src for ds, name, src in self.copied if ds == dataset_id}


def run(api, dataset_ids, destination=None, mode=NameConflict.RENAME, progress=None):
    destination = destination or Destination()
    return merge_datasets(
        api, api.source, META, api.source_datasets(*dataset_ids), destination, mode, workspace_id=5, progress=progress
    )


@pytest.mark.parametrize("project_type", ["images", "videos"])
def test_new_project_gets_source_meta_and_every_item_with_renamed_conflicts(project_type):
    api = FakeApi(project_type)
    done = []

    result = run(api, [1, 3, 4], progress=done.append)

    project, dataset = api.created
    assert (project.name, project.workspace_id, project.type) == ("my_Project", 5, project_type)
    assert sly.ProjectMeta.from_json(api.metas[project.id]) == META
    assert (dataset.name, dataset.project_id) == ("my_dataset", project.id)
    e = api.ext
    # train (a, b) > hard (a); val (a, c); in tree order
    assert api.copied_from(dataset.id) == {f"a{e}": 11, f"b{e}": 12, f"a_01{e}": 21, f"a_02{e}": 31, f"c{e}": 32}
    assert result == MergeResult(project, dataset, datasets_merged=4, items_merged=5, items_ignored=0)
    assert sum(done) == 5


def test_image_annotations_are_copied_as_json():
    api = FakeApi("images")
    run(api, [1])
    new_ids = {name: item.id for item in api.items[api.created[1].id] for name in [item.name]}
    assert api.uploaded_anns[new_ids["a.jpg"]] == api.anns[11]
    assert api.uploaded_anns[new_ids["b.jpg"]] == api.anns[12]


def test_video_annotations_are_rebuilt_with_the_destination_meta():
    api = FakeApi("videos")
    run(api, [1])
    new_ids = {item.name: item.id for item in api.items[api.created[1].id]}
    ann = api.uploaded_anns[new_ids["b.mp4"]]
    assert isinstance(ann, sly.VideoAnnotation)
    assert (
        ann.to_json(sly.KeyIdMap())["frames"]
        == sly.VideoAnnotation.from_json(api.anns[12], META, sly.KeyIdMap()).to_json(sly.KeyIdMap())["frames"]
    )


@pytest.mark.parametrize("project_type", ["images", "videos"])
def test_ignore_skips_taken_names_and_counts_them(project_type):
    api = FakeApi(project_type)
    done = []
    result = run(api, [1, 3], Destination(20, dataset_id=200), NameConflict.IGNORE, done.append)

    e = api.ext
    assert api.copied_from(200) == {f"b{e}": 12, f"c{e}": 32}
    assert (result.items_merged, result.items_ignored, result.datasets_merged) == (2, 3, 3)
    assert sum(done) == 5
    assert result.message(api.source) == (
        "3 datasets from project 'fruits' have been successfully merged to the dataset: 'merged' in project "
        "'target'. Items ignored: 3"
    )


@pytest.mark.parametrize("project_type", ["images", "videos"])
def test_dataset_prefix(project_type):
    api = FakeApi(project_type)
    run(api, [1, 3], Destination(20, dataset_id=200), NameConflict.DATASET_PREFIX)
    e = api.ext
    assert api.copied_from(200) == {
        f"train_a{e}": 11,
        f"b{e}": 12,
        f"hard_a{e}": 21,
        f"val_a{e}": 31,
        f"c{e}": 32,
    }


def test_existing_project_gets_merged_meta_and_a_new_dataset():
    api = FakeApi(dst_meta=sly.ProjectMeta(obj_classes=[sly.ObjClass("pear", sly.Point)]))
    result = run(api, [3], Destination(20, dataset_name="extra"))

    (dataset,) = api.created
    assert (dataset.name, dataset.project_id) == ("extra", 20)
    assert {c.name for c in sly.ProjectMeta.from_json(api.metas[20]).obj_classes} == {"pear", "lemon", "kiwi"}
    assert api.copied_from(dataset.id) == {"a.jpg": 31, "c.jpg": 32}
    assert result.project.id == 20


def test_meta_conflict_fails_before_anything_is_created_or_copied():
    api = FakeApi(dst_meta=sly.ProjectMeta(obj_classes=[KIWI_POLYGON]))
    before = dict(api.metas)
    with pytest.raises(MetaConflict):
        run(api, [1], Destination(20, dataset_id=200))
    assert api.created == [] and api.copied == [] and api.metas == before


def test_destination_dataset_is_never_merged_into_itself():
    api = FakeApi()
    api.datasets[200] = api.datasets[200]._replace(project_id=10)  # destination inside the source project
    api.projects[20] = api.source
    result = run(api, [200, 3], Destination(10, dataset_id=200))

    assert api.copied_from(200) == {"a_01.jpg": 31, "c.jpg": 32}
    assert result.datasets_merged == 1


def test_batches_of_fifty(monkeypatch):
    api = FakeApi()
    api.items[4] = [api._item(5000 + i, f"img{i}") for i in range(120)]
    api.anns.update({item.id: api._ann(item.id) for item in api.items[4]})
    done = []
    run(api, [4], progress=done.append)
    assert done == [50, 50, 20]
    assert len(api.copied) == 120
