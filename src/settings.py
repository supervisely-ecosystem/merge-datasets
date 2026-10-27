"""Task context, read once at startup. The app has no modal options: everything is chosen in the GUI."""

from __future__ import annotations

from dataclasses import dataclass

import supervisely as sly


@dataclass(frozen=True)
class Settings:
    project_id: int

    @classmethod
    def from_env(cls) -> Settings:
        """The platform passes the project as `modal.state.slyProjectId` / `context.projectId`."""
        project_id = sly.env.project_id(raise_not_found=False)
        if project_id is None:
            raise ValueError("No project in the task context: run the app from a project's context menu")
        return cls(project_id=project_id)
