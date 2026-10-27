"""Item names in the destination dataset: how a name conflict is resolved."""

from __future__ import annotations

import os
from enum import StrEnum


class NameConflict(StrEnum):
    """What to do with an item whose name the destination dataset already has (values = old GUI state)."""

    IGNORE = "ignore"  # skip the item
    RENAME = "rename"  # IMG_555.jpeg -> IMG_555_01.jpeg
    DATASET_PREFIX = "dsrename"  # IMG_555.jpeg -> Dataset1_IMG_555.jpeg (-> Dataset1_IMG_555_01.jpeg if taken too)


def free_name(used: set[str] | frozenset[str], name: str) -> str:
    """`name`, or `<stem>_01<ext>`, `<stem>_02<ext>`, ... - the first one not in `used`.

    Same result as `supervisely._utils.generate_free_name(used, name, with_ext=True)`, without its
    set copy per attempt (quadratic on large datasets).
    """
    if name not in used:
        return name
    stem, ext = os.path.splitext(name)
    suffix = 1
    while (candidate := f"{stem}_{suffix:02d}{ext}") in used:
        suffix += 1
    return candidate


def resolve_name(name: str, dataset_name: str, used: set[str], mode: NameConflict) -> str | None:
    """Destination name for an item `name` from source dataset `dataset_name`, or None to skip it.

    The chosen name is added to `used`, so later items of the same run see it as taken.
    """
    if name in used:
        if mode is NameConflict.IGNORE:
            return None
        if mode is NameConflict.DATASET_PREFIX:
            name = f"{dataset_name}_{name}"
        name = free_name(used, name)
    used.add(name)
    return name
