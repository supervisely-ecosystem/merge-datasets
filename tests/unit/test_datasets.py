from types import SimpleNamespace as NS

from src.core.datasets import build_tree, path, walk, with_nested

# root a (1) > b (2) > c (3); root d (4); e (5) under d, listed before its parent on purpose
DATASETS = [
    NS(id=5, name="e", parent_id=4),
    NS(id=1, name="a", parent_id=None),
    NS(id=2, name="b", parent_id=1),
    NS(id=3, name="c", parent_id=2),
    NS(id=4, name="d", parent_id=None),
]


def ids(datasets):
    return [ds.id for ds in datasets]


def test_tree_order_puts_parents_first_and_keeps_sibling_order():
    roots = build_tree(DATASETS)
    assert [n.dataset.id for n in roots] == [1, 4]
    assert ids(walk(roots)) == [1, 2, 3, 4, 5]


def test_orphan_becomes_a_root():
    assert [n.dataset.id for n in build_tree([NS(id=9, name="x", parent_id=77)])] == [9]


def test_path():
    assert path(DATASETS[3], DATASETS) == "a/b/c"
    assert path(DATASETS[4], DATASETS) == "d"


def test_selecting_a_parent_takes_its_nested_datasets_once():
    assert ids(with_nested(DATASETS, [2])) == [2, 3]
    assert ids(with_nested(DATASETS, [1, 3, 2])) == [1, 2, 3]
    assert ids(with_nested(DATASETS, [5, 4])) == [4, 5]
    assert ids(with_nested(DATASETS, [3, 5])) == [3, 5]


def test_nothing_selected():
    assert with_nested(DATASETS, []) == []
