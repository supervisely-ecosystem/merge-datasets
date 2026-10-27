import pytest

from src.core.names import NameConflict
from src.core.options import Destination, GuiChoice, InvalidChoice, MergeOptions


def test_defaults_are_the_old_gui_defaults():
    options = GuiChoice(dataset_ids=(1,)).to_options()
    assert options == MergeOptions((1,), Destination(None, "my_Project", None, "my_dataset"), NameConflict.RENAME)
    assert options.destination.new_project and options.destination.new_dataset


def test_new_project_always_gets_a_new_dataset():
    choice = GuiChoice(dataset_ids=(1,), dataset_mode="existingDataset", dataset_id=7, project_id=3)
    assert choice.to_options().destination == Destination(None, "my_Project", None, "my_dataset")


def test_existing_project_and_dataset():
    choice = GuiChoice(
        dataset_ids=(1, 2),
        name_conflict="dsrename",
        project_mode="existingProject",
        project_id=3,
        dataset_mode="existingDataset",
        dataset_id=7,
    )
    options = choice.to_options()
    assert options.destination == Destination(3, "my_Project", 7, "my_dataset")
    assert options.name_conflict is NameConflict.DATASET_PREFIX
    assert not options.destination.new_project and not options.destination.new_dataset


def test_existing_project_new_dataset():
    choice = GuiChoice(dataset_ids=(1,), project_mode="existingProject", project_id=3, dataset_name=" merged ")
    assert choice.to_options().destination == Destination(3, "my_Project", None, "merged")


@pytest.mark.parametrize(
    ("choice", "message"),
    [
        (GuiChoice(), "Please, select at least one dataset to merge"),
        (GuiChoice(dataset_ids=(1,), project_name=" "), "Please, define the name of a new Project"),
        (GuiChoice(dataset_ids=(1,), project_mode="existingProject"), "Please, select one of the existing Projects"),
        (GuiChoice(dataset_ids=(1,), dataset_name=""), "Please, define the name of a new Dataset"),
        (
            GuiChoice(dataset_ids=(1,), project_mode="existingProject", project_id=3, dataset_mode="existingDataset"),
            "Please, select one of the existing Datasets",
        ),
    ],
)
def test_incomplete_choice(choice, message):
    with pytest.raises(InvalidChoice, match=message):
        choice.to_options()
