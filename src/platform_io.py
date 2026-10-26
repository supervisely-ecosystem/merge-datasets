"""Every Supervisely API call the app makes."""

from __future__ import annotations

from collections.abc import Sequence

import supervisely as sly
from supervisely.video_annotation.key_id_map import KeyIdMap

SUPPORTED_TYPES = (str(sly.ProjectType.IMAGES), str(sly.ProjectType.VIDEOS))


def get_project(api: sly.Api, project_id: int) -> tuple[sly.ProjectInfo, sly.ProjectMeta]:
    project = api.project.get_info_by_id(project_id, raise_error=True)
    if project.type not in SUPPORTED_TYPES:
        raise ValueError(
            f"Project {project.name!r} has type {project.type!r}; the app works only with images and videos projects"
        )
    return project, get_meta(api, project_id)


def get_project_info(api: sly.Api, project_id: int) -> sly.ProjectInfo:
    return api.project.get_info_by_id(project_id, raise_error=True)


def get_meta(api: sly.Api, project_id: int) -> sly.ProjectMeta:
    return sly.ProjectMeta.from_json(api.project.get_meta(project_id))


def update_meta(api: sly.Api, project_id: int, meta: sly.ProjectMeta) -> None:
    api.project.update_meta(project_id, meta.to_json())


def list_projects(api: sly.Api, workspace_id: int, project_type: str) -> list[sly.ProjectInfo]:
    """Projects of one type in a workspace (candidates for "Add to existing Project")."""
    return [p for p in api.project.get_list(workspace_id) if p.type == project_type]


def list_datasets(api: sly.Api, project_id: int) -> list[sly.DatasetInfo]:
    return api.dataset.get_list(project_id, recursive=True)


def create_project(api: sly.Api, workspace_id: int, name: str, project_type: str) -> sly.ProjectInfo:
    return api.project.create(workspace_id, name, type=project_type, change_name_if_conflict=True)


def create_dataset(api: sly.Api, project_id: int, name: str) -> sly.DatasetInfo:
    return api.dataset.create(project_id, name, change_name_if_conflict=True)


def get_dataset(api: sly.Api, dataset_id: int) -> sly.DatasetInfo:
    return api.dataset.get_info_by_id(dataset_id, raise_error=True)


def list_items(api: sly.Api, project_type: str, dataset_id: int) -> list:
    if project_type == str(sly.ProjectType.VIDEOS):
        return api.video.get_list(dataset_id)
    return api.image.get_list(dataset_id)


def copy_images(
    api: sly.Api, src_dataset_id: int, dst_dataset_id: int, images: Sequence[sly.ImageInfo], names: Sequence[str]
) -> None:
    """Add the images to the destination by id (no pixel re-upload), then their annotations as they are."""
    anns = api.annotation.download_batch(src_dataset_id, [image.id for image in images])
    ann_by_id = {ann.image_id: ann.annotation for ann in anns}
    new_images = api.image.upload_ids(dst_dataset_id, list(names), [image.id for image in images])
    api.annotation.upload_jsons(
        [image.id for image in new_images],
        [ann_by_id[image.id] for image in images],
        skip_bounds_validation=True,
    )


def copy_videos(
    api: sly.Api,
    src_dataset_id: int,
    dst_dataset_id: int,
    videos: Sequence[sly.api.video.video_api.VideoInfo],
    names: Sequence[str],
    dst_meta: sly.ProjectMeta,
) -> None:
    """Add the videos to the destination by hash or link (no re-upload), then their annotations."""
    anns = api.video.annotation.download_bulk(src_dataset_id, [video.id for video in videos])
    ann_by_id = {ann["videoId"]: ann for ann in anns}
    new_videos = api.video.upload_ids(dst_dataset_id, list(names), [video.id for video in videos], infos=list(videos))
    for video, new_video in zip(videos, new_videos, strict=True):
        ann = sly.VideoAnnotation.from_json(ann_by_id[video.id], dst_meta, KeyIdMap())
        api.video.annotation.append(new_video.id, ann)


def set_task_output(api: sly.Api, project: sly.ProjectInfo) -> None:
    task_id = sly.env.task_id(raise_not_found=False)
    if task_id is not None:
        api.task.set_output_project(task_id, project.id, project.name)


def register_workflow_input(api: sly.Api, project_id: int) -> None:
    api.app.workflow.add_input_project(project_id)


def register_workflow_output(api: sly.Api, project_id: int) -> None:
    api.app.workflow.add_output_project(project_id)
