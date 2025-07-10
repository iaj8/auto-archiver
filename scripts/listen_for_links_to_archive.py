#!/usr/bin/env python
# coding: utf-8

from google.cloud import pubsub_v1
from google.oauth2 import service_account
import json
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import time
import os
import subprocess

from sync_drive_and_gcs import rsync_gdrive_and_other_storages
from compute_story_local_timezone import compute_and_enter_story_local_timezone
from duplicate_utils import flag_duplicates
import sys
import yaml

service_account_path = "../secrets/service_account.json"
project_id = "vi-stg-a29a"

gcs_bucket_name = 'vi_workflow'
authenticated_url_prefix = f"https://storage.cloud.google.com/{gcs_bucket_name}"
link_col = 'B'

credentials = service_account.Credentials.from_service_account_file(service_account_path)
subscriber = pubsub_v1.SubscriberClient(credentials=credentials)

message_queue = Queue()
job_semaphores = {}

max_workers = 5


def callback(message):
    print(f"Received message: {message}")
    message_data = message.data.decode('utf-8')
    try:
        message_dict = json.loads(message_data)
    except json.JSONDecodeError as e:
        print("Failed to decode JSON data.")
        message.ack()
        return

    job_id = message_dict['spreadsheetId']

    if job_id not in job_semaphores:
        job_semaphores[job_id] = {
            'run_auto_archiver': threading.Semaphore(1),
            # 'rsync_gdrive_and_gcs': threading.Semaphore(1)
        }

    message_queue.put(message_dict)
    message.ack()


def worker(worker_id, executor):
    while True:
        message_dict = message_queue.get()  # Get a message from the queue
        if message_dict is None:
            break  # Exit the worker if None is found in the queue

        job_id = message_dict['spreadsheetId']
        print(f"Worker {worker_id}: processing message: {message_dict}")

        # if link_col not in message_dict['range']:
        #     message_queue.task_done()
        #     return

        try:
            print(f"Worker {worker_id}: trying to acquire {job_id} archiver semaphor")
            with job_semaphores[job_id]['run_auto_archiver']:
                print(f"Worker {worker_id}: running auto-archiver")
                future = executor.submit(run_auto_archiver, message_dict)
                result = future.result()
                print(f"Worker {worker_id}: auto-archiver complete, running sync")
                
            # print(f"Worker {worker_id}: trying to acquire {job_id} sync semaphor")
            # with job_semaphores[job_id]['rsync_gdrive_and_gcs']:
            
                top_level_drive_folder = message_dict["driveFolderId"]
                top_level_gcs_folder = message_dict["projectName"]
                sheet_id = message_dict['spreadsheetId']
                worksheet_name = message_dict['sheetName']
                project_name = message_dict["projectName"]
                
                lucid_storage = "Yes" in message_dict["saveToLucid"] if "saveToLucid" in message_dict else False
                trint_storage = "Yes" in message_dict["sendToTrint"] if "sendToTrint" in message_dict else False
                trint_workspace = message_dict["trintWorkspaceId"] if "trintWorkspaceId" in message_dict else ""
                trint_folder = message_dict["trintFolderId"] if "trintFolderId" in message_dict else ""

                print("service_account_path", service_account_path)
                print("top_level_drive_folder", top_level_drive_folder)
                print("gcs_bucket_name", gcs_bucket_name)
                print("top_level_gcs_folder", top_level_gcs_folder)
                print("sheet_id", sheet_id)
                print("worksheet_name", worksheet_name)
                print("authenticated_url_prefix", authenticated_url_prefix)
                print("project_name", project_name)
                print("lucid_storage", lucid_storage)
                print("trint_storage", trint_storage)
                print("trint_workspace", trint_workspace)
                print("trint_folder", trint_folder)

                future_2 = executor.submit(
                    rsync_gdrive_and_other_storages, service_account_path, 
                    top_level_drive_folder, gcs_bucket_name, 
                    top_level_gcs_folder, sheet_id, worksheet_name, 
                    authenticated_url_prefix, project_name, lucid_storage,
                    trint_storage, trint_workspace, trint_folder
                )
                result_2 = future_2.result()
                print(f"Worker {worker_id}: sync complete")

        except (KeyboardInterrupt, Exception) as e:
            print(f"Error during running of job {job_id}: {e}")

        finally:
            print(f"Worker {worker_id}: finished processing message: {message_dict}")
            message_queue.task_done()

def run_auto_archiver(message_dict):
    # from pprint import pprint
    # pprint(message_dict)
    # return
    sheet_id = message_dict['spreadsheetId']
    root_folder_id = message_dict["driveFolderId"]
    project_name = message_dict["projectName"]
    worksheet_name = message_dict['sheetName']

    naming_convention = message_dict["mediaNamingConvention"] if "mediaNamingConvention" in message_dict else "only_uar"
    lucid_storage = "Yes" in message_dict["saveToLucid"] if "saveToLucid" in message_dict else False
    trint_storage = "Yes" in message_dict["sendToTrint"] if "sendToTrint" in message_dict else False
    trint_workspace = message_dict["trintWorkspaceId"] if "trintWorkspaceId" in message_dict else ""
    trint_folder = message_dict["trintFolderId"] if "trintFolderId" in message_dict else ""

    try:
        compute_and_enter_story_local_timezone(service_account_path, sheet_id, worksheet_name)
    except:
        pass

    # Overwrite the config file with the storages for this project
    
    with open("../vi-config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    existing_storages = config.get("steps", {}).get("storages", [])

    if not lucid_storage and "local_storage" in existing_storages:
        existing_storages.remove("local_storage")
    if not trint_storage and "trint_storage" in existing_storages:
        existing_storages.remove("trint_storage")

    if lucid_storage:
        existing_storages.append("local_storage")

    if trint_storage:
        existing_storages.append("trint_storage")

    existing_storages = list(set(existing_storages))
    
    config.setdefault("steps", {})["storages"] = existing_storages
    
    with open("../vi-config-generated.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    command = f"""cd .. && python -m src.auto_archiver"""
    command += f' --config vi-config-generated.yaml'
    command += f' --gsheet_feeder.sheet_id "{sheet_id}"'
    command += f' --gdrive_storage.root_folder_id "{root_folder_id}"'
    command += f' --project_name.value "{project_name}"'
    command += f' --project_naming_convention.value "{naming_convention}"'
    command += f' --gcs_storage_1.top_level_folder "{project_name}"'
    command += f' --gcs_storage_2.top_level_folder "{project_name}"'

    if lucid_storage:
        command += f' --local_storage.save_to "/media/filespace/VI/{project_name}/media"'
    if trint_storage:
        command += f' --trint_storage.workspace_id "{trint_workspace}"'
        command += f' --trint_storage.folder_id "{trint_folder}"'

    print(command)
    result = subprocess.run(command, shell=True, check=True)

    try:
        flag_duplicates(service_account_path, sheet_id, worksheet_name)
    except:
        pass

    return result

subscription_id = sys.argv[1] #"vi_worfklow_subscription"
subscription_path = subscriber.subscription_path(project_id, subscription_id)

executor = ThreadPoolExecutor(max_workers=max_workers)

num_workers = max_workers
threads = []
for i in range(num_workers):
    thread = threading.Thread(target=worker, args=(i, executor))
    thread.start()
    threads.append(thread)

# Subscribe to the subscription
streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
print(f"Listening for messages on {subscription_path}...\n")

try:
    streaming_pull_future.result()  # Block and wait for messages
except KeyboardInterrupt:
    streaming_pull_future.cancel()  # Trigger the shutdown
    streaming_pull_future.result()  # Block until the shutdown is complete