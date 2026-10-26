"""Copies the items of the selected datasets into one destination dataset."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import supervisely as sly

from src import platform_io
from src.core.names import NameConflict, resolve_name
from src.core.options import Destination

BATCH_SIZE = 50

META_CONFLICT_MESSAGE = (
    "Error during merge, source project meta has conflics with destination project meta. "
    "Please check shapes of classes / types of tags with the same names or select another destination. "
)


class MetaConflict(Exception):
    """Classes or tags of the source project are incompatible with the destination project."""


@dataclass(frozen=True)
class MergeResult:
    project: sly.ProjectInfo
    dataset: sly.DatasetInfo
    datasets_merged: int
    items_merged: int
    items_ignored: int

    def message(self, source: sly.ProjectInfo) -> str:
        text = (
            f"{self.datasets_merged} datasets from project '{source.name}' have been successfully merged "
            f"to the dataset: '{self.dataset.name}' in project '{self.project.name}'."
        )
        if self.items_ignored > 0:
            text += f" Items ignored: {self.items_ignored}"
        return text


def prepare_destination(
    api: sly.Api,
    source: sly.ProjectInfo,
    source_meta: sly.ProjectMeta,
    destination: Destination,
    workspace_id: int,
) -> tuple[sly.ProjectInfo, sly.DatasetInfo, sly.ProjectMeta]:
    """Create or open the destination project and dataset; the destination meta gets the source classes and tags.

    A new project goes to `workspace_id` with the source type and meta (the name gets `_001`, ... when taken).
    An existing project keeps its meta merged with the source one; raises MetaConflict before anything is
    created when they disagree (same class name with another shape, same tag name with another value type).
    """
    if destination.new_project:
        project = platform_io.create_project(api, workspace_id, destination.project_name, source.type)
        platform_io.update_meta(api, project.id, source_meta)
        meta = source_meta.clone()
    else:
        project = platform_io.get_project_info(api, destination.project_id)
        try:
            meta = platform_io.get_meta(api, project.id).merge(source_meta)
        except Exception as e:  # noqa: BLE001 - the SDK raises plain ValueError/KeyError subclasses here
            raise MetaConflict(str(e)) from e
        platform_io.update_meta(api, project.id, meta)

    if destination.new_dataset:
        dataset = platform_io.create_dataset(api, project.id, destination.dataset_name)
    else:
        dataset = platform_io.get_dataset(api, destination.dataset_id)
    return project, dataset, meta


def merge_datasets(
    api: sly.Api,
    source: sly.ProjectInfo,
    source_meta: sly.ProjectMeta,
    datasets: Sequence[sly.DatasetInfo],
    destination: Destination,
    name_conflict: NameConflict,
    workspace_id: int,
    progress: Callable[[int], object] | None = None,
) -> MergeResult:
    """Copy every item of `datasets` (no nesting: each dataset's own items) into one destination dataset.

    Items are added by id with their annotations. Names already in the destination are resolved by
    `name_conflict`. The destination dataset itself is never read as a source. `progress` is called with
    the number of items handled (copied or ignored) after every batch.
    """
    project, dataset, meta = prepare_destination(api, source, source_meta, destination, workspace_id)
    sly.logger.info(
        f"Destination: project {project.name!r} (id {project.id}), dataset {dataset.name!r} (id {dataset.id})"
    )

    used = {item.name for item in platform_io.list_items(api, source.type, dataset.id)}
    merged = ignored = datasets_merged = 0
    for src_dataset in datasets:
        if src_dataset.id == dataset.id:
            sly.logger.info(f"Dataset {src_dataset.name!r} is the destination; it is not merged into itself")
            continue
        datasets_merged += 1
        items = platform_io.list_items(api, source.type, src_dataset.id)
        sly.logger.info(f"Merging {len(items)} items from dataset {src_dataset.name!r}")
        for batch in sly.batched(items, BATCH_SIZE):
            kept, names = [], []
            for item in batch:
                name = resolve_name(item.name, src_dataset.name, used, name_conflict)
                if name is None:
                    sly.logger.info(f"Item {item.name!r} from {src_dataset.name!r} is ignored: the name is taken")
                    continue
                kept.append(item)
                names.append(name)
            if kept:
                if source.type == str(sly.ProjectType.VIDEOS):
                    platform_io.copy_videos(api, src_dataset.id, dataset.id, kept, names, meta)
                else:
                    platform_io.copy_images(api, src_dataset.id, dataset.id, kept, names)
            merged += len(kept)
            ignored += len(batch) - len(kept)
            if progress is not None:
                progress(len(batch))

    return MergeResult(platform_io.get_project_info(api, project.id), dataset, datasets_merged, merged, ignored)
