"""Dataset tree helpers on DatasetInfo-like objects (`id`, `name`, `parent_id`)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


@dataclass
class Node[D]:
    dataset: D
    children: list[Node[D]] = field(default_factory=list)


def build_tree[D](datasets: Sequence[D]) -> list[Node[D]]:
    """Roots of the dataset tree; siblings keep the order of `datasets`.

    A dataset whose parent is not in `datasets` becomes a root.
    """
    nodes = {ds.id: Node(ds) for ds in datasets}
    roots = []
    for ds in datasets:
        parent = nodes.get(ds.parent_id) if ds.parent_id is not None else None
        (parent.children if parent is not None else roots).append(nodes[ds.id])
    return roots


def walk[D](roots: Iterable[Node[D]]) -> list[D]:
    """Datasets in tree order: every parent before its children (depth first)."""
    result = []
    for node in roots:
        result.append(node.dataset)
        result.extend(walk(node.children))
    return result


def path[D](dataset: D, datasets: Sequence[D]) -> str:
    """`parent/child` path of a dataset inside its project."""
    by_id = {ds.id: ds for ds in datasets}
    parts = [dataset.name]
    while dataset.parent_id is not None and dataset.parent_id in by_id:
        dataset = by_id[dataset.parent_id]
        parts.append(dataset.name)
    return "/".join(reversed(parts))


def with_nested[D](datasets: Sequence[D], selected_ids: Iterable[int]) -> list[D]:
    """The selected datasets and every dataset nested in them, in tree order.

    Each dataset appears once even if it is selected together with its parent.
    """
    selected = set(selected_ids)
    result = []

    def visit(nodes: list[Node[D]], inside_selected: bool) -> None:
        for node in nodes:
            take = inside_selected or node.dataset.id in selected
            if take:
                result.append(node.dataset)
            visit(node.children, take)

    visit(build_tree(datasets), False)
    return result
