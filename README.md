<div align="center" markdown>
<img src="https://user-images.githubusercontent.com/48245050/182392835-74ef1899-fde8-459a-a628-b5ab5ed35210.png"/>

# Merge Datasets

<p align="center">
  <a href="#Overview">Overview</a> •
  <a href="#How-To-Run">How To Run</a> •
  <a href="#How-To-Use">How To Use</a>
</p>

[![](https://img.shields.io/badge/supervisely-ecosystem-brightgreen)](https://ecosystem.supervisely.com/apps/supervisely-ecosystem/merge-datasets)
[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervisely.com/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/merge-datasets)
[![views](https://app.supervisely.com/img/badges/views/supervisely-ecosystem/merge-datasets.png)](https://supervisely.com)
[![runs](https://app.supervisely.com/img/badges/runs/supervisely-ecosystem/merge-datasets.png)](https://supervisely.com)

</div>

# Overview

The application merges the selected datasets of a project into a single dataset. It works with `images` and
`videos` projects. Items are added to the destination without re-uploading files, together with their annotations
(objects, tags, video frames). The source datasets are not changed.

- **Nested datasets**: selecting a dataset also selects the datasets nested in it. The items of every selected
  dataset end up in one flat destination dataset.
- **Destination**: a new project (in the same workspace, with the classes and tags of the source project) or an
  existing project of the same type in the workspace. In an existing project the items go to a new or an existing
  dataset, and the classes and tags of the source project are added to the destination project.
- **Name conflicts**: items in different datasets can have the same name. Choose what happens when the destination
  dataset already has an item with that name:
  - ignore the item;
  - add it with an auto-generated name: `IMG_555.jpeg` → `IMG_555_01.jpeg`;
  - add the source dataset name to the item name: `IMG_555.jpeg` → `Dataset1_IMG_555.jpeg`
    (and `Dataset1_IMG_555_01.jpeg` if that name is taken too).

The merge stops with an error, before anything is created, when the source and the destination project have a class
with the same name but another shape, or a tag with the same name but another value type.

# How To Run

**Step 1.** Add the app to your team from the [Ecosystem](https://ecosystem.supervisely.com/apps/merge-datasets) if it is not there.

**Step 2.** Open the context menu of an images or videos project → `Run App` → `Merge Datasets`.

<img src="https://i.imgur.com/6ecS2ec.png" width="600px"/>

**Step 3.** Open the application from the `Tasks` page.

<img src="https://i.imgur.com/U1kaHGb.png"/>

# How To Use

<img src="https://i.imgur.com/lnAcG3I.png"/>

1. Your source project.
2. Select the datasets to merge (nested datasets of a selected dataset are included).
3. Choose how to resolve name conflicts.
4. Choose the destination project: a new one (its name; a free name is generated if it is taken) or an existing one.
5. Choose the destination dataset: a new one (its name; a free name is generated if it is taken) or, in an existing
   project, an existing dataset. A dataset is never merged into itself.
6. Press `Merge Datasets`. A notification shows how many datasets were merged and how many items were ignored.

The task output links to the destination project. The session stays open, so you can run another merge; stop the
application from the `Tasks` page when you are done.

<img src="https://i.imgur.com/36yQ86G.png" />

Watch a short video for more details (it shows an earlier version of the interface):

<a data-key="sly-embeded-video-link" href="https://www.youtube.com/watch?v=vfUjJXeWVY8" data-video-code="vfUjJXeWVY8">
    <img src="https://i.imgur.com/LSBR9vG.png" alt="SLY_EMBEDED_VIDEO_LINK"  style="max-width:500px;">
</a>
