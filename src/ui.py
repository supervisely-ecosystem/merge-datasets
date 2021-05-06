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

    state["nameConflicts"] = "ignore"
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


def set_init_project_fields(api, task_id, datasets, src_project_type, src_project_name, src_project_id,
                            src_project_preview, is_finished):
    fields = [
        {"field": "state.srcDatasetList", "payload": datasets},
        {"field": "data.srcProjectType", "payload": src_project_type},
        {"field": "data.srcProjectName", "payload": src_project_name},
        {"field": "data.projectId", "payload": src_project_id},
        {"field": "data.srcProjectPreviewUrl", "payload": src_project_preview},
        {"field": "data.finished", "payload": is_finished}
    ]
    api.app.set_fields(task_id, fields)


def item_progress(api, task_id, message, curr_item_count, total_items, is_finished):
    fields = [
        {"field": "data.progressName", "payload": message},
        {"field": "data.currentProgressLabel", "payload": curr_item_count},
        {"field": "data.totalProgressLabel", "payload": total_items},
        {"field": "data.currentProgress", "payload": curr_item_count},
        {"field": "data.totalProgress", "payload": total_items},
        {"field": "data.finished", "payload": is_finished}
    ]
    api.app.set_fields(task_id, fields)
