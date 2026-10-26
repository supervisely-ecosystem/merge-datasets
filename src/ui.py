"""GUI: source project, datasets to merge, name-conflict policy, destination project and dataset, Merge button."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import supervisely as sly
from supervisely.app.widgets import (
    Button,
    Card,
    Container,
    Field,
    Input,
    OneOf,
    Progress,
    ProjectThumbnail,
    RadioGroup,
    Select,
    Text,
    TreeSelect,
)

from src.core.datasets import Node, build_tree, with_nested
from src.core.names import NameConflict
from src.core.options import (
    DEFAULT_DATASET_NAME,
    DEFAULT_PROJECT_NAME,
    DatasetMode,
    GuiChoice,
    InvalidChoice,
    MergeOptions,
    ProjectMode,
)
from src.merger import META_CONFLICT_MESSAGE, MergeResult, MetaConflict

ProgressFn = Callable[[int], object]


@dataclass(frozen=True)
class Actions:
    """Everything the GUI needs from the platform; `main.py` wires it to the API."""

    list_source_datasets: Callable[[], list[sly.DatasetInfo]]
    list_projects: Callable[[], list[sly.ProjectInfo]]  # candidates for "Add to existing Project"
    list_datasets: Callable[[int], list[sly.DatasetInfo]]  # datasets of a destination project
    merge: Callable[[MergeOptions, list[sly.DatasetInfo], ProgressFn], MergeResult]
    merged: Callable[[MergeResult], None]


def tree_items(datasets: Sequence[sly.DatasetInfo]) -> list[TreeSelect.Item]:
    def convert(nodes: list[Node]) -> list[TreeSelect.Item]:
        return [TreeSelect.Item(id=n.dataset.id, label=n.dataset.name, children=convert(n.children)) for n in nodes]

    return convert(build_tree(datasets))


def project_items(projects: Sequence[sly.ProjectInfo]) -> list[Select.Item]:
    return [Select.Item(project.id, f"{project.name} (id {project.id})") for project in projects]


class MergeGui:
    def __init__(self, project: sly.ProjectInfo, actions: Actions):
        self._project = project
        self._actions = actions
        self._datasets = actions.list_source_datasets()

        # 2. datasets: checking a dataset checks the datasets nested in it
        self.datasets = TreeSelect(tree_items(self._datasets), multiple_select=True, flat=False, append_to_body=False)

        # 3. settings
        self.name_conflict = RadioGroup(
            [
                RadioGroup.Item(
                    NameConflict.IGNORE, "Ignore item if destination dataset already has item with the same name"
                ),
                RadioGroup.Item(
                    NameConflict.RENAME,
                    "Add item with the new auto-generated name (example: IMG_555.jpeg -> IMG_555_01.jpeg)",
                ),
                RadioGroup.Item(
                    NameConflict.DATASET_PREFIX,
                    "Add dataset name to the item name (example: IMG_555.jpeg -> Dataset1_IMG_555.jpeg)",
                ),
            ],
            direction="vertical",
        )
        self.name_conflict.set_value(NameConflict.RENAME)

        self.project_name = Input(DEFAULT_PROJECT_NAME, placeholder="Please input project name")
        self.dst_project = Select(project_items(actions.list_projects()), filterable=True, placeholder="Select project")
        if any(item.value == project.id for item in self.dst_project.get_items()):
            self.dst_project.set_value(project.id)  # merging into the source project is the common case
        self.project_mode = RadioGroup(
            [
                RadioGroup.Item(
                    ProjectMode.NEW,
                    "Create new Project",
                    Field(
                        self.project_name,
                        "",
                        "If Project with the same name already exists, a new name will be generated automatically",
                    ),
                ),
                RadioGroup.Item(ProjectMode.EXISTING, "Add to existing Project", self.dst_project),
            ]
        )

        self.dataset_name = Input(DEFAULT_DATASET_NAME, placeholder="Please input dataset name")
        self.dst_dataset = TreeSelect([], multiple_select=False, flat=True, append_to_body=False)
        self.dataset_mode = RadioGroup(
            [
                RadioGroup.Item(
                    DatasetMode.NEW,
                    "Create new Dataset",
                    Field(
                        self.dataset_name,
                        "",
                        "If dataset with the same name already exists, a new name will be generated automatically",
                    ),
                ),
                RadioGroup.Item(DatasetMode.EXISTING, "Add to existing dataset", self.dst_dataset),
            ]
        )
        self.dataset_mode.hide()  # a new project gets a new dataset

        self.merge_button = Button("Merge Datasets", icon="zmdi zmdi-play")
        self.error = Text("", "error")
        self.error.hide()
        self.progress = Progress(hide_on_finish=True)

        input_card = Card("1. Input Project", content=ProjectThumbnail(_thumbnail_info(project)))
        datasets_card = Card("2. Select the datasets that should be merged", content=self.datasets)
        settings_card = Card(
            "3. Merge Settings",
            "Configure merging settings and destination",
            content=Container(
                [
                    Field(
                        self.name_conflict,
                        "How to solve name conflicts?",
                        "Items within a single datasets have unique names. But items in different datasets can have "
                        "the same names. Name conflicts arise when these datasets are merged.",
                    ),
                    Field(
                        Container([self.project_mode, OneOf(self.project_mode)]),
                        "Destination Project",
                        "Define destination project",
                    ),
                    Field(
                        Container([self.dataset_mode, OneOf(self.dataset_mode)]),
                        "Destination Dataset",
                        "Define destination dataset",
                    ),
                    self.merge_button,
                    self.error,
                    self.progress,
                ]
            ),
        )
        self.layout = Container([input_card, datasets_card, settings_card])

        self.project_mode.value_changed(self._on_project_mode)
        self.dst_project.value_changed(self._on_dst_project)
        self.merge_button.click(self.run)

    # --- events

    def _on_project_mode(self, mode: str) -> None:
        if mode == ProjectMode.EXISTING:
            self.dataset_mode.show()
            self._load_dst_datasets(self.dst_project.get_value())
        else:
            self.dataset_mode.set_value(DatasetMode.NEW)
            self.dataset_mode.hide()

    def _on_dst_project(self, project_id: int | None) -> None:
        self._load_dst_datasets(project_id)

    def _load_dst_datasets(self, project_id: int | None) -> None:
        self.dst_dataset.clear_selected()
        self.dst_dataset.set_items(tree_items(self._actions.list_datasets(project_id)) if project_id else [])

    def choice(self) -> GuiChoice:
        selected = self.datasets.get_selected() or []
        dst_dataset = self.dst_dataset.get_selected()
        return GuiChoice(
            dataset_ids=tuple(item.id for item in selected),
            name_conflict=self.name_conflict.get_value(),
            project_mode=self.project_mode.get_value(),
            project_name=self.project_name.get_value() or "",
            project_id=self.dst_project.get_value(),
            dataset_mode=self.dataset_mode.get_value(),
            dataset_name=self.dataset_name.get_value() or "",
            dataset_id=dst_dataset.id if dst_dataset is not None else None,
        )

    def run(self) -> None:
        try:
            options = self.choice().to_options()
        except InvalidChoice as e:
            self.error.set(str(e), "error")
            self.error.show()
            return
        self.error.hide()

        datasets = with_nested(self._datasets, options.dataset_ids)
        total = sum(ds.items_count or 0 for ds in datasets if ds.id != options.destination.dataset_id)
        self._set_locked(True)
        try:
            with self.progress(message="Items Merged", total=total) as bar:
                result = self._actions.merge(options, datasets, bar.update)
        except MetaConflict:
            sly.app.show_dialog("Error", META_CONFLICT_MESSAGE, status="error")
            return
        finally:
            self._set_locked(False)

        self._actions.merged(result)
        sly.app.show_dialog("Merge completed", result.message(self._project), status="info")
        self._refresh()

    def _refresh(self) -> None:
        """After a merge: a new project or dataset may now exist (the session stays open for another merge)."""
        self._datasets = self._actions.list_source_datasets()
        selected = [item.id for item in self.datasets.get_selected() or []]
        self.datasets.set_items(tree_items(self._datasets))
        self.datasets.set_selected_by_id(selected)
        current = self.dst_project.get_value()
        self.dst_project.set(project_items(self._actions.list_projects()))
        if current is not None:
            self.dst_project.set_value(current)
        if self.project_mode.get_value() == ProjectMode.EXISTING:
            selected_dataset = self.dst_dataset.get_selected()
            self._load_dst_datasets(self.dst_project.get_value())
            if selected_dataset is not None:
                self.dst_dataset.set_selected_by_id(selected_dataset.id)

    def _set_locked(self, locked: bool) -> None:
        self.merge_button.loading = locked
        for widget in (
            self.datasets,
            self.name_conflict,
            self.project_mode,
            self.project_name,
            self.dst_project,
            self.dataset_mode,
            self.dataset_name,
            self.dst_dataset,
        ):
            if locked:
                widget.disable()
            else:
                widget.enable()


def _thumbnail_info(project: sly.ProjectInfo) -> sly.ProjectInfo:
    """ProjectThumbnail fails on a project without items (no preview url); show it without a preview."""
    if project.reference_image_url is None:
        return project._replace(reference_image_url="")
    return project
