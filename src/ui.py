import supervisely_lib as sly
from functools import partial


def init_context(data, team_id, workspace_id, project_id):
    data["teamId"] = team_id
    data["workspaceId"] = workspace_id
    data["projectId"] = project_id


def init_options(data, state):
    state["dstProjectMode"] = "newProject"
    state["dstProjectName"] = "my_Project"
    state["dstProjectId"] = None

    state["dstDatasetMode"] = "newDataset"
    state["dstDatasetName"] = "my_dataset"
    state["selectedDatasetName"] = None

    state["nameConflicts"] = "rename"
    state["srcDatasetList"] = []
    state["selectedDatasets"] = []

    data["srcProjectType"] = None
    data["srcProjectName"] = None
    data["resultProjectPreviewUrl"] = None
    data["processing"] = False
    data["finished"] = False


def init_progress(data, state):
    data["progressName"] = None
    data["currentProgressLabel"] = 0
    data["totalProgressLabel"] = 0
    data["currentProgress"] = 0
    data["totalProgress"] = 0


def init_project_fields(api, task_id, datasets, src_project):
    fields = [
        {"field": "state.srcDatasetList", "payload": datasets},
        {"field": "data.srcProjectType", "payload": src_project.type},
        {"field": "data.srcProjectName", "payload": src_project.name},
        {"field": "data.projectId", "payload": src_project.id},
        {"field": "data.srcProjectPreviewUrl", "payload": api.image.preview_url(src_project.reference_image_url,
                                                                                      100, 100)},
        {"field": "data.finished", "payload": False}
    ]
    api.app.set_fields(task_id, fields)


def _set_progress(api, task_id, message, current, total):
    fields = [
        {"field": "data.progressName", "payload": message},
        {"field": "data.currentProgressLabel", "payload": current},
        {"field": "data.totalProgressLabel", "payload": total},
        {"field": "data.currentProgress", "payload": current},
        {"field": "data.totalProgress", "payload": total},
        {"field": "data.finished", "payload": False}
    ]
    api.app.set_fields(task_id, fields)


def _update_progress_ui(api, task_id, progress: sly.Progress):
    _set_progress(api, task_id, progress.message, progress.current, progress.total)


def update_progress(count, api: sly.Api, task_id, progress: sly.Progress):
    count = min(count, progress.total - progress.current)
    progress.iters_done(count)
    if progress.need_report():
        progress.report_progress()
        _update_progress_ui(api, task_id, progress)


def set_progress(current, api: sly.Api, task_id, progress: sly.Progress):
    old_value = progress.current
    delta = current - old_value
    update_progress(delta, api, task_id, progress)


def get_progress_cb(api, task_id, message, total, is_size=False, func=update_progress):
    progress = sly.Progress(message, total, is_size=is_size)
    progress_cb = partial(func, api=api, task_id=task_id, progress=progress)
    return progress_cb
