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

    ui.set_init_project_fields(api, task_id, datasets, src_project.type, src_project.name, src_project.id,
                               api.image.preview_url(src_project.reference_image_url, 100, 100), "false")


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
                                  "Please stop and re-run application manually.", level="error")
            raise e

        dst_dataset = None
        if state["dstDatasetMode"] == "existingDataset":
            dst_dataset = api.dataset.get_info_by_name(dst_project.id, dst_selected_dataset)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}'.")
        elif state["dstDatasetMode"] == "newDataset":
            if api.dataset.exists(dst_project.id, dst_dataset_name):
                existing_datasets = [dataset_info.name for dataset_info in api.dataset.get_list(dst_project.id)]
                old_dst_dataset_name = dst_dataset_name
                dst_dataset_name = generate_free_name(existing_datasets, dst_dataset_name)
                app_logger.info(
                    f"Dataset with the given name '{old_dst_dataset_name}' already exists. Dataset: '{dst_dataset_name}' will be created.")

            dst_dataset = api.dataset.create(dst_project.id, dst_dataset_name)
            app_logger.info(f"Destination Dataset: name'{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")

    elif state["dstProjectMode"] == "newProject":
        if api.project.exists(WORKSPACE_ID, dst_project_name):
            existing_projects = [project_info.name for project_info in api.project.get_list(WORKSPACE_ID)]
            old_dst_project_name = dst_project_name
            dst_project_name = generate_free_name(existing_projects, dst_project_name)
            app_logger.info(
                f"Project with the given name '{old_dst_project_name}' already exists. Project: `{dst_project_name}` will be created.")

        dst_project = api.project.create(WORKSPACE_ID, dst_project_name, type=src_project.type)

        if src_project.type == str(sly.ProjectType.VIDEOS):
            dst_meta = sly.ProjectMeta()
            dst_meta = dst_meta.merge(src_meta)

        api.project.update_meta(dst_project.id, src_meta.to_json())

        dst_dataset = api.dataset.create(dst_project.id, dst_dataset_name)
        app_logger.info(f"Destination Project: name '{dst_project.name}', id:'{dst_project.id}' has been created.")
        app_logger.info(f"Destination Dataset: name '{dst_dataset.name}', id:'{dst_dataset.id}' has been created.")

    app_logger.info("Merging info", extra={
        "project name": src_project.name,
        "project id": src_project.id,
        "datasets to merge": state['selectedDatasets']
    })

    existing_items = []

    if src_project.type == str(sly.ProjectType.IMAGES):
        existing_images = api.image.get_list(dst_dataset.id)
        for image in existing_images:
            existing_items.append(image.name)
    elif src_project.type == str(sly.ProjectType.VIDEOS):
        existing_videos = api.video.get_list(dst_dataset.id)
        for video in existing_videos:
            existing_items.append(video.name)

    cur_item_count = 0
    progress = sly.Progress("Merging", total_items)
    for dataset_name in state["selectedDatasets"]:
        dataset = src_datasets_by_name[dataset_name.lstrip('/')]

        if src_project.type == str(sly.ProjectType.IMAGES):
            images = api.image.get_list(dataset.id)
            app_logger.info(f"Merging images and annotations from '{dataset.name}' dataset")

            for batch in sly.batched(images):
                ds_image_ids = [ds_image_info.id for ds_image_info in batch]
                ds_image_names = [ds_image_info.name for ds_image_info in batch]
                ann_infos = api.annotation.download_batch(dataset.id, ds_image_ids)
                ann_jsons = [ann_info.annotation for ann_info in ann_infos]

                indexes = []
                for i, ds_image_name in enumerate(ds_image_names):
                    if ds_image_name in existing_items and state["nameConflicts"] == "rename":
                        ds_image_names[i] = generate_free_name(existing_items, ds_image_name, True)
                    elif ds_image_name in existing_items and state["nameConflicts"] == "ignore":
                        app_logger.info(
                            f"Image with name: `{ds_image_name}` already exists in dataset: `{dataset.name}` "
                            f"and will be ignored.")
                        indexes.append(i)
                        continue

                    existing_items.append(ds_image_names[i])

                if len(indexes) > 0:
                    for index in sorted(indexes, reverse=True):
                        del ds_image_names[index]
                        del ds_image_ids[index]
                        del ann_jsons[index]

                if len(ds_image_names) == 0:
                    continue

                dst_images = api.image.upload_ids(dst_dataset.id, ds_image_names, ds_image_ids)
                dst_image_ids = [dst_img_info.id for dst_img_info in dst_images]
                api.annotation.upload_jsons(dst_image_ids, ann_jsons)

                cur_item_count = cur_item_count + len(ds_image_ids)
                ui.item_progress(api, task_id, "Items Merged", cur_item_count, total_items, "false")
                progress.iters_done_report(len(ds_image_ids))

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
                    if ds_video_name in existing_items and state["nameConflicts"] == "rename":
                        ds_video_name = generate_free_name(existing_items, ds_video_name, with_ext=True)
                    elif ds_video_name in existing_items and state["nameConflicts"] == "ignore":
                        app_logger.info(f"Video with name: '{ds_video_name}' already exists in dataset: '{dataset.name}' and will be ignored.")
                        continue

                    dst_video = api.video.upload_hash(dst_dataset.id, ds_video_name, ds_video_hash)
                    api.video.annotation.append(dst_video.id, ann)
                    existing_items.append(ds_video_name)

                    cur_item_count = cur_item_count + 1
                    ui.item_progress(api, task_id, "Items Merged", cur_item_count, total_items, "false")
                    progress.iter_done_report()

    if state["nameConflicts"] == "ignore":
        app.show_modal_window(f"{len(state['selectedDatasets'])} datasets, from Project: '{src_project.name}' "
                              f"has been successfully merged to dataset: '{dst_dataset.name}', in Project: '{dst_project.name}' "
                              f"Items ignored: {total_items - cur_item_count}"
                              , level="info")
    else:
        app.show_modal_window(f"Datasets: `{len(state['selectedDatasets'])}`, from Project: '{src_project.name}' "
                              f"has been successfully merged to Dataset: '{dst_dataset.name}', in Project: '{dst_project.name}'"
                              , level="info")


    fields = [
        {"field": "data.processing", "payload": "false"},
        {"field": "state.selectedDatasets", "payload": 0},
        {"field": "data.finished", "payload": "true"}
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