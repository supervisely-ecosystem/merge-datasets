import os
import supervisely_lib as sly
from supervisely_lib._utils import generate_free_name
from supervisely_lib.video_annotation.key_id_map import KeyIdMap
import ui

app: sly.AppService = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])

global src_meta
global src_project
global src_datasets_by_name


def _get_names(f, dataset_id):
    infos = f(dataset_id)
    return [info.name for info in infos]


@app.callback("init_src_project")
@sly.timeit
def init_src_project(api: sly.Api, task_id, context, state, app_logger):
    global src_project, src_meta, src_datasets_by_name, total_items

    src_project = api.project.get_info_by_id(PROJECT_ID)
    src_meta_json = api.project.get_meta(PROJECT_ID)
    src_meta = sly.ProjectMeta.from_json(src_meta_json)

    src_datasets = api.dataset.get_list(PROJECT_ID)

    src_datasets_by_name = {}
    for dataset in src_datasets:
        src_datasets_by_name[dataset.name] = dataset

    total_items = 0
    datasets = []
    for dataset in src_datasets:
        datasets.append({
            "path": "/" + dataset.name,
            "type": "dataset",
            "id": dataset.id,
            "items count": dataset.items_count,
        })
        total_items += dataset.items_count

    ui.init_project_fields(api, task_id, datasets, src_project)


@app.callback("merge_projects")
@sly.timeit
def merge_projects(api: sly.Api, task_id, context, state, app_logger):
    dst_project_id = state["dstProjectId"]
    dst_project_name = state["dstProjectName"]

    dst_selected_dataset = state["selectedDatasetName"]
    dst_dataset_name = state["dstDatasetName"]

    dst_project = None
    if state["dstProjectMode"] == "existingProject":
        dst_project = api.project.get_info_by_id(dst_project_id)
        dst_meta_json = api.project.get_meta(dst_project_id)
        dst_meta = sly.ProjectMeta.from_json(dst_meta_json)
        try:
            dst_meta = dst_meta.merge(src_meta)
            api.project.update_meta(dst_project.id, dst_meta.to_json())
            app_logger.info(f"Destination Project: name: '{dst_project.name}', id: '{dst_project.id}'.")
        except Exception as e:
            app.show_modal_window("Error during merge, source project meta has conflics with destination project meta. "
                                  "Please check shapes of classes / types of tags with the same names or select another destination. "
                                  , level = "error")
            fields = [
                {"field": "data.processing", "payload": False},
                {"field": "state.selectedDatasetName", "payload": None},
            ]
            api.task.set_fields(task_id, fields)
            return

        dst_dataset = None
        if state["dstDatasetMode"] == "existingDataset":
            dst_dataset = api.dataset.get_info_by_name(dst_project.id, dst_selected_dataset)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}'.")
        elif state["dstDatasetMode"] == "newDataset":
            dst_dataset = api.dataset.create(dst_project.id, dst_dataset_name, change_name_if_conflict=True)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")

    elif state["dstProjectMode"] == "newProject":
        dst_project = api.project.create(WORKSPACE_ID, dst_project_name, type=src_project.type, change_name_if_conflict=True)
        api.project.update_meta(dst_project.id, src_meta.to_json())
        dst_dataset = api.dataset.create(dst_project.id, dst_dataset_name)
        app_logger.info(f"Destination Project: name '{dst_project.name}', id:'{dst_project.id}' has been created.")
        app_logger.info(f"Destination Dataset: name '{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")

    app_logger.info("Merging info", extra={
        "project name": src_project.name,
        "project id": src_project.id,
        "datasets to merge": state['selectedDatasets']
    })

    existing_names = []
    if src_project.type == str(sly.ProjectType.IMAGES):
        existing_names = _get_names(api.image.get_list, dst_dataset.id)
    elif src_project.type == str(sly.ProjectType.VIDEOS):
        existing_names = _get_names(api.video.get_list, dst_dataset.id)

    ignored_items = 0
    progress_items_cb = ui.get_progress_cb(api, task_id, "Items Merged", total_items)
    for dataset_name in state["selectedDatasets"]:
        dataset = src_datasets_by_name[dataset_name.lstrip('/')]

        if src_project.type == str(sly.ProjectType.IMAGES):
            images = api.image.get_list(dataset.id)
            app_logger.info(f"Merging images and annotations from '{dataset.name}' dataset")

            for batch in sly.batched(images):
                batch_ids = [image_info.id for image_info in batch]
                batch_anns = api.annotation.download_batch(dataset.id, batch_ids)
                ids = []
                names = []
                anns_jsons = []
                for img_info, ann_info in zip(batch, batch_anns):
                    new_name = generate_free_name(existing_names, img_info.name, True)
                    if state["nameConflicts"] == "ignore" and new_name != img_info.name:
                        ignored_items += 1
                        app_logger.info(
                            f"Image with name: '{new_name}' already exists in dataset: '{dataset.name}' and will be ignored.")

                    ids.append(img_info.id)
                    names.append(new_name)
                    existing_names.append(new_name)
                    anns_jsons.append(ann_info.annotation)

                if len(ids) > 0:
                    dst_images = api.image.upload_ids(dst_dataset.id, names, ids)
                    dst_ids = [dst_info.id for dst_info in dst_images]
                    api.annotation.upload_jsons(dst_ids, anns_jsons)

                progress_items_cb(len(names))

        elif src_project.type == str(sly.ProjectType.VIDEOS):
            dst_meta = src_meta
            key_id_map = KeyIdMap()
            videos = api.video.get_list(dataset.id)
            app_logger.info(f"Merging videos and annotations from '{dataset.name}' dataset")
            for batch in sly.batched(videos):
                video_ids = [video_info.id for video_info in batch]
                video_names = [video_info.name for video_info in batch]
                video_hashes = [video_info.hash for video_info in batch]
                for video_id, video_name, video_hash in zip(video_ids, video_names, video_hashes):
                    ann_info = api.video.annotation.download(video_id)
                    ann = sly.VideoAnnotation.from_json(ann_info, dst_meta, key_id_map)
                    if video_name in existing_names and state["nameConflicts"] == "rename":
                        video_name = generate_free_name(existing_names, video_name, with_ext=True)
                    elif video_name in existing_names and state["nameConflicts"] == "ignore":
                        ignored_items += 1
                        app_logger.info(f"Video with name: '{video_name}' already exists in dataset: '{dataset.name}' and will be ignored.")
                        progress_items_cb(1)
                        continue

                    progress_items_cb(1)

                    dst_video = api.video.upload_hash(dst_dataset.id, video_name, video_hash)
                    api.video.annotation.append(dst_video.id, ann)
                    existing_names.append(video_name)


    if state["nameConflicts"] == "ignore":
        app.show_modal_window(f"{len(state['selectedDatasets'])} datasets, from project: '{src_project.name}' "
                              f"has been successfully merged to dataset: '{dst_dataset.name}', in project: '{dst_project.name}' "
                              f"Items ignored: {ignored_items}"
                              , level="info")
    else:
        app.show_modal_window(f"Datasets: `{len(state['selectedDatasets'])}`, from project: '{src_project.name}' "
                              f"has been successfully merged to dataset: '{dst_dataset.name}', in project: '{dst_project.name}'"
                              , level="info")


    fields = [
        {"field": "data.processing", "payload": False},
        {"field": "state.selectedDatasets", "payload": 0},
        {"field": "data.finished", "payload": True}
    ]
    api.app.set_fields(task_id, fields)


def main():
    data = {}
    state = {}

    ui.init_context(data, TEAM_ID, WORKSPACE_ID, PROJECT_ID)
    ui.init_options(data, state)
    ui.init_progress(data, state)

    app.run(data=data, state=state, initial_events=[{"command": "init_src_project"}])


if __name__ == "__main__":
    sly.main_wrapper("main", main)