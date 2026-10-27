"""What the user chose in the GUI, checked and turned into merge options."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.core.names import NameConflict

DEFAULT_PROJECT_NAME = "my_Project"
DEFAULT_DATASET_NAME = "my_dataset"


class ProjectMode(StrEnum):  # values = old GUI state `dstProjectMode`
    NEW = "newProject"
    EXISTING = "existingProject"


class DatasetMode(StrEnum):  # values = old GUI state `dstDatasetMode`
    NEW = "newDataset"
    EXISTING = "existingDataset"


@dataclass(frozen=True)
class Destination:
    """Where the items go. `project_id` None = new project (its dataset is always new);
    `dataset_id` None = new dataset. Names are used only for what is created."""

    project_id: int | None = None
    project_name: str = DEFAULT_PROJECT_NAME
    dataset_id: int | None = None
    dataset_name: str = DEFAULT_DATASET_NAME

    @property
    def new_project(self) -> bool:
        return self.project_id is None

    @property
    def new_dataset(self) -> bool:
        return self.dataset_id is None


@dataclass(frozen=True)
class MergeOptions:
    dataset_ids: tuple[int, ...]
    destination: Destination
    name_conflict: NameConflict = NameConflict.RENAME


class InvalidChoice(ValueError):
    """The GUI choice is incomplete; the message is what the old GUI showed under the disabled button."""


@dataclass(frozen=True)
class GuiChoice:
    """Raw values of the GUI controls."""

    dataset_ids: tuple[int, ...] = ()
    name_conflict: str = NameConflict.RENAME
    project_mode: str = ProjectMode.NEW
    project_name: str = DEFAULT_PROJECT_NAME
    project_id: int | None = None
    dataset_mode: str = DatasetMode.NEW
    dataset_name: str = DEFAULT_DATASET_NAME
    dataset_id: int | None = None

    def to_options(self) -> MergeOptions:
        """Checked options; raises InvalidChoice. A new project always gets a new dataset."""
        if not self.dataset_ids:
            raise InvalidChoice("Please, select at least one dataset to merge")
        project_mode = ProjectMode(self.project_mode)
        dataset_mode = DatasetMode.NEW if project_mode is ProjectMode.NEW else DatasetMode(self.dataset_mode)

        if project_mode is ProjectMode.NEW and not self.project_name.strip():
            raise InvalidChoice("Please, define the name of a new Project")
        if project_mode is ProjectMode.EXISTING and self.project_id is None:
            raise InvalidChoice("Please, select one of the existing Projects")
        if dataset_mode is DatasetMode.NEW and not self.dataset_name.strip():
            raise InvalidChoice("Please, define the name of a new Dataset")
        if dataset_mode is DatasetMode.EXISTING and self.dataset_id is None:
            raise InvalidChoice("Please, select one of the existing Datasets")

        destination = Destination(
            project_id=self.project_id if project_mode is ProjectMode.EXISTING else None,
            project_name=self.project_name.strip(),
            dataset_id=self.dataset_id if dataset_mode is DatasetMode.EXISTING else None,
            dataset_name=self.dataset_name.strip(),
        )
        return MergeOptions(tuple(self.dataset_ids), destination, NameConflict(self.name_conflict))
