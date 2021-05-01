import os
import supervisely_lib as sly
from supervisely_lib._utils import generate_free_name
from supervisely_lib.video_annotation.key_id_map import KeyIdMap
import ui

app: sly.AppService = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.projectId'])

global src_meta
global src_project
global src_datasets_by_name


@app.callback("init_src_project")
@sly.timeit
def init_src_project(api: sly.Api, task_id, context, state, app_logger):
    global src_project, src_meta, src_meta_json, src_datasets_by_name

    src_project = api.project.get_info_by_id(PROJECT_ID)
    src_meta_json = api.project.get_meta(PROJECT_ID)
    src_meta = sly.ProjectMeta.from_json(src_meta_json)

    src_datasets = api.dataset.get_list(PROJECT_ID)

    src_datasets_by_name = {}
    for dataset in src_datasets:
        src_datasets_by_name[dataset.name] = dataset

    dataset_items = 0
    datasets = []
    for dataset in src_datasets:
        datasets.append({
            "path": "/" + dataset.name,
            "type": "dataset",
            "id": dataset.id,
            "items count": dataset.items_count,
        })
        dataset_items += dataset.items_count

    fields = [
        {"field": "state.srcDatasetList", "payload": datasets},
        {"field": "data.srcProjectType", "payload": src_project.type},
        {"field": "data.srcProjectName", "payload": src_project.name},
        {"field": "data.projectId", "payload": src_project.id},
        {"field": "data.srcProjectPreviewUrl",
         "payload": api.image.preview_url(src_project.reference_image_url, 100, 100)},
        {"field": "data.finished", "payload": "false"}
    ]
    api.app.set_fields(task_id, fields)


@app.callback("merge_projects")
@sly.timeit
def merge_projects(api: sly.Api, task_id, context, state, app_logger):

    DST_PROJECT_ID = state["dstProjectId"]
    DST_PROJECT_NAME = state["dstProjectName"]

    DST_DATASET_ID = state["dstDatasetId"]
    DST_DATASET_NAME = state["dstDatasetName"]

    # CHECK IF MERGE DESTINATION EXISTS OR NOT
    dst_project = None
    if state["dstProjectMode"] == "existingProject":
        dst_project = api.project.get_info_by_id(DST_PROJECT_ID)
        dst_meta_json = api.project.get_meta(DST_PROJECT_ID)
        dst_meta = sly.ProjectMeta.from_json(dst_meta_json)
        try:
            dst_meta.merge(src_meta)
            app_logger.info(f"Destination Project: name'{dst_project.name}', id:'{dst_project.id}'.")
        except Exception as e:
            app_logger.error("Source Project Meta is conflicting with Destination Project Meta. Please check that classes geometry matches in both projects.")
            raise e

        dst_dataset = None
        if state["dstDatasetMode"] == "existingDataset":
            dst_dataset = api.dataset.get_info_by_id(DST_DATASET_ID)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}'.")
        elif state["dstDatasetMode"] == "newDataset":
            if api.dataset.exists(dst_project.id, DST_DATASET_NAME):
                app_logger.info(
                    f"Dataset with the given name '{DST_DATASET_NAME}' already exists. Dataset: '{api.dataset.get_free_name(dst_project.id, DST_DATASET_NAME)}' will be created.")
                DST_DATASET_NAME = api.dataset.get_free_name(dst_project.id, DST_DATASET_NAME)

            dst_dataset = api.dataset.create(dst_project.id, DST_DATASET_NAME)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")

    elif state["dstProjectMode"] == "newProject":
        if api.project.exists(WORKSPACE_ID, DST_PROJECT_NAME):
            app_logger.info(
                f"Project with the given name '{DST_PROJECT_NAME}' already exists. Project: `{api.project.get_free_name(WORKSPACE_ID, DST_PROJECT_NAME)}` will be created.")
            DST_PROJECT_NAME = api.project.get_free_name(WORKSPACE_ID, DST_PROJECT_NAME)

        dst_project = api.project.create(WORKSPACE_ID, DST_PROJECT_NAME, type=src_project.type)

        dst_meta = sly.ProjectMeta()
        dst_meta = dst_meta.merge(src_meta)
        api.project.update_meta(dst_project.id, dst_meta.to_json())

        dst_dataset = api.dataset.create(dst_project.id, DST_DATASET_NAME)
        app_logger.info(f"Destination Project: name '{dst_project.name}', id:'{dst_project.id}' has been created.")
        app_logger.info(f"Destination Dataset: name '{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")
    # CHECK IF MERGE DESTINATION EXISTS OR NOT

    # MERGING PROCESS
    app_logger.info(f"Merging Project: name: '{src_project.name}', id: '{src_project.id}', datasets to merge: {len(state['selectedDatasets'])}")

    total_items = 0
    for dataset_name in state["selectedDatasets"]:
        dataset = src_datasets_by_name[dataset_name.lstrip('/')]
        total_items += dataset.items_count

    fields = [
        {"field": "data.progressName", "payload": None},
        {"field": "data.currentProgressLabel", "payload": 0},
        {"field": "data.totalProgressLabel", "payload": total_items},
        {"field": "data.currentProgress", "payload": 0},
        {"field": "data.totalProgress", "payload": total_items},
        {"field": "data.finished", "payload": "false"}
    ]
    api.app.set_fields(task_id, fields)

    uploaded_items = []
    cur_item_count = 0
    for dataset_name in state["selectedDatasets"]:
        dataset = src_datasets_by_name[dataset_name.lstrip('/')]

        # IMAGES
        if src_project.type == str(sly.ProjectType.IMAGES):
            images = api.image.get_list(dataset.id)
            app_logger.info(f"Merging images and annotations from '{dataset.name}' dataset")
            for batch in sly.batched(images):
                ds_image_ids = [ds_image_info.id for ds_image_info in batch]
                ds_image_names = [ds_image_info.name for ds_image_info in batch]
                ann_infos = api.annotation.download_batch(dataset.id, ds_image_ids)
                ann_jsons = [ann_info.annotation for ann_info in ann_infos]
                for ds_image_id, ds_image_name, ann_info, ann_json in zip(ds_image_ids, ds_image_names, ann_infos,
                                                                          ann_jsons):

                    if ds_image_name in uploaded_items and state["handleItemNameConflicts"] == "True":
                        ds_image_name = generate_free_name(uploaded_items, ds_image_name, with_ext=False)
                    elif ds_image_name in uploaded_items and state["handleItemNameConflicts"] == "False":
                        app_logger.info(f"Image with name: `{ds_image_name}` is already exists in dataset: `{dataset.name}` and will be ignored.")
                        continue


                    dst_image = api.image.upload_id(dst_dataset.id, ds_image_name, ds_image_id)
                    api.annotation.upload_json(dst_image.id, ann_json)
                    uploaded_items.append(dst_image.name)

                    progress_items_cb = ui.get_progress_cb(api, task_id, 1, message=f"{ds_image_name}",
                                                           total=total_items, func=ui.set_progress)
                    cur_item_count = cur_item_count + 1
                    fields = [
                        {"field": "data.progressName", "payload": "Items Merged"},
                        {"field": "data.currentProgressLabel", "payload": cur_item_count},
                        {"field": "data.totalProgressLabel", "payload": total_items},
                        {"field": "data.currentProgress", "payload": cur_item_count},
                        {"field": "data.totalProgress", "payload": total_items},
                        {"field": "data.finished", "payload": "false"}
                    ]
                    api.app.set_fields(task_id, fields)
        # IMAGES

        # VIDEOS
        elif src_project.type == str(sly.ProjectType.VIDEOS):
            videos = api.video.get_list(dataset.id)
            app_logger.info(f"Merging videos and annotations from '{dataset.name}' dataset")
            for batch in sly.batched(videos):
                ds_video_ids = [video_info.id for video_info in batch]
                ds_video_names = [video_info.name for video_info in batch]
                ds_video_hashes = [video_info.hash for video_info in batch]
                for ds_video_id, ds_video_name, ds_video_hash in zip(ds_video_ids, ds_video_names, ds_video_hashes):
                    ann_info = api.video.annotation.download(ds_video_id)
                    ann = sly.VideoAnnotation.from_json(ann_info, dst_meta, KeyIdMap())
                    if ds_video_name in uploaded_items and state["handleItemNameConflicts"] is True:
                        ds_video_name = generate_free_name(uploaded_items, ds_video_name, with_ext=True)
                    elif ds_video_name in uploaded_items and state["handleItemNameConflicts"] is False:
                        app_logger.info(f"Video with name: '{ds_video_name}' is already exists in dataset: '{dataset.name}' and will be ignored.")
                        continue

                    dst_video = api.video.upload_hash(dst_dataset.id, ds_video_name, ds_video_hash)
                    api.video.annotation.append(dst_video.id, ann)

                    progress_items_cb = ui.get_progress_cb(api, task_id, 1, message=f"{ds_video_name}",
                                                           total=total_items, func=ui.set_progress)
                    cur_item_count = cur_item_count + 1
                    fields = [
                        {"field": "data.progressName", "payload": "Items Merged"},
                        {"field": "data.currentProgressLabel", "payload": cur_item_count},
                        {"field": "data.totalProgressLabel", "payload": total_items},
                        {"field": "data.currentProgress", "payload": cur_item_count},
                        {"field": "data.totalProgress", "payload": total_items},
                        {"field": "data.finished", "payload": "false"}
                    ]
                    api.app.set_fields(task_id, fields)
        # VIDEOS
    app.show_modal_window(
        f"{len(state['selectedDatasets'])} Datasets, from Project: {src_project.name}' has been successfully merged to Dataset: '{dst_dataset.name}' in Project: '{dst_project.name}'.", level="info")

    fields = [
        {"field": "data.processing", "payload": "false"},
        {"field": "state.selectedDatasets", "payload": 0},
        {"field": "data.finished", "payload": "true"}
    ]
    api.app.set_fields(task_id, fields)

    # MERGING PROCESS

    app.stop()


def main():
    data = {}
    state = {}

    ui.init_context(data, TEAM_ID, WORKSPACE_ID, PROJECT_ID)
    #ui.init_connection(data, state)
    ui.init_options(data, state)
    ui.init_progress(data, state)

    app.run(data=data, state=state, initial_events=[{"command": "init_src_project"}])


if __name__ == "__main__":
    sly.main_wrapper("main", main)