"""Merge Datasets: GUI app started from an images or videos project's context menu.

Run with `uvicorn src.main:app` (see config.json `entrypoint`). This module is the composition root:
it reads the task context, creates the Api and wires the GUI to the merge and the platform outputs.
"""

from __future__ import annotations

import os

import supervisely as sly
from dotenv import load_dotenv

from src import platform_io
from src.core.options import MergeOptions
from src.merger import MergeResult, merge_datasets
from src.settings import Settings
from src.ui import Actions, MergeGui


def create_app() -> sly.Application:
    if not sly.is_production():
        load_dotenv("local.env")
        load_dotenv(os.path.expanduser("~/supervisely.env"))

    settings = Settings.from_env()
    api = sly.Api.from_env()
    project, meta = platform_io.get_project(api, settings.project_id)

    def merge(options: MergeOptions, datasets: list[sly.DatasetInfo], progress) -> MergeResult:
        platform_io.register_workflow_input(api, project.id)
        sly.logger.info(
            "Merging datasets",
            extra={"project_id": project.id, "datasets": [ds.id for ds in datasets], "options": str(options)},
        )
        return merge_datasets(
            api, project, meta, datasets, options.destination, options.name_conflict, project.workspace_id, progress
        )

    def merged(result: MergeResult) -> None:
        platform_io.set_task_output(api, result.project)
        platform_io.register_workflow_output(api, result.project.id)
        sly.logger.info(result.message(project), extra={"project_id": result.project.id})

    actions = Actions(
        list_source_datasets=lambda: platform_io.list_datasets(api, project.id),
        list_projects=lambda: platform_io.list_projects(api, project.workspace_id, project.type),
        list_datasets=lambda project_id: platform_io.list_datasets(api, project_id),
        merge=merge,
        merged=merged,
    )
    gui = MergeGui(project, actions)
    return sly.Application(layout=gui.layout)


app = create_app()
