import random

import pytest
from supervisely._utils import generate_free_name

from src.core.names import NameConflict, free_name, resolve_name


@pytest.mark.parametrize(
    ("used", "name", "expected"),
    [
        (set(), "a.jpg", "a.jpg"),
        ({"a.jpg"}, "a.jpg", "a_01.jpg"),
        ({"a.jpg", "a_01.jpg"}, "a.jpg", "a_02.jpg"),
        ({"a.tar.gz"}, "a.tar.gz", "a.tar_01.gz"),
        ({"noext"}, "noext", "noext_01"),
        ({".hidden"}, ".hidden", ".hidden_01"),
    ],
)
def test_free_name(used, name, expected):
    assert free_name(used, name) == expected


def test_free_name_matches_the_sdk_helper_on_random_names():
    rng = random.Random(7)
    stems = ["IMG_1", "IMG_1_01", "a", "a.b", ".x", "v"]
    exts = [".jpg", ".jpeg", ".mp4", "", ".tar.gz"]
    for _ in range(2000):
        used = {rng.choice(stems) + rng.choice(["", "_01", "_02", "_03"]) + rng.choice(exts) for _ in range(6)}
        name = rng.choice(stems) + rng.choice(exts)
        assert free_name(used, name) == generate_free_name(used, name, with_ext=True)


def test_free_name_does_not_change_used():
    used = {"a.jpg"}
    free_name(used, "a.jpg")
    assert used == {"a.jpg"}


def test_no_conflict_keeps_the_name_in_every_mode():
    for mode in NameConflict:
        used = {"b.jpg"}
        assert resolve_name("a.jpg", "ds", used, mode) == "a.jpg"
        assert used == {"a.jpg", "b.jpg"}


def test_ignore_skips_a_taken_name_and_leaves_used_alone():
    used = {"a.jpg"}
    assert resolve_name("a.jpg", "ds", used, NameConflict.IGNORE) is None
    assert used == {"a.jpg"}


def test_rename_adds_a_numeric_suffix():
    used = {"a.jpg"}
    assert resolve_name("a.jpg", "ds", used, NameConflict.RENAME) == "a_01.jpg"
    assert resolve_name("a.jpg", "ds", used, NameConflict.RENAME) == "a_02.jpg"
    assert used == {"a.jpg", "a_01.jpg", "a_02.jpg"}


def test_dataset_prefix_then_suffix_when_the_prefixed_name_is_taken_too():
    used = {"a.jpg"}
    assert resolve_name("a.jpg", "ds1", used, NameConflict.DATASET_PREFIX) == "ds1_a.jpg"
    assert resolve_name("a.jpg", "ds1", used, NameConflict.DATASET_PREFIX) == "ds1_a_01.jpg"


def test_modes_keep_the_old_gui_values():
    assert [m.value for m in NameConflict] == ["ignore", "rename", "dsrename"]
