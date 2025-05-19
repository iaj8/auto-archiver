#!/usr/bin/env python
# coding: utf-8

from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.cloud import storage
from googleapiclient.http import MediaIoBaseDownload
import io
import os
from pprint import pprint
import base64
from google.api_core import retry
from datetime import datetime, timedelta

import os
from google.cloud import storage

import gspread
from gspread.exceptions import APIError
import random
import string
import ffmpeg
import hashlib
from time import sleep
import yaml
import requests
import shutil

RETRY_POLICY = retry.Retry(deadline=1200)
SCOPES = ['https://www.googleapis.com/auth/drive']

MANUAL_UPL_HIGHLIGHT_COLOR = {
    "red": 0.85,
    "green": 0.4,
    "blue": 0.78
}

def create_uar(project_name, row):
    random_string = ''.join(random.choices(string.ascii_lowercase, k=2))
    return f"""{row}_{project_name}_{random_string}"""

def convert_base64_md5(md5_hash_base64):
    md5_hash_hex = base64.b64decode(md5_hash_base64).hex()
    return md5_hash_hex

def list_files_in_drive_folder(service, folder_id, is_shared_drive=True):

    query_params = {
        "q": f"'{folder_id}' in parents",
        "fields": "files(id, name, mimeType, thumbnailLink, md5Checksum)"
    }
    
    if is_shared_drive:
        query_params.update({
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True
        })

    results = service.files().list(**query_params).execute()
    files = results.get('files', [])
    return {
            file['name']: {
                'checksum': file['md5Checksum'] if 'md5Checksum' in file else None,
                'id': file['id'] if 'id' in file else None,
                'mimeType': file['mimeType'] if 'mimeType' in file else None,
                'thumbnailLink':  file['thumbnailLink'] if 'thumbnailLink' in file else None
            } for file in files
            }

def get_media_duration_and_sha3_512(uar, file_data, content_type, get_hash=True):
    temp_filename = f"""{uar}.{content_type[content_type.find("/")+1:]}"""
    with open(temp_filename, 'wb') as temp_file:
        temp_file.write(file_data.read())

    try:
        probe = ffmpeg.probe(temp_filename)
        duration = float(probe['format']['duration'])
        duration = f"""{str(timedelta(seconds=duration))}"""

    except Exception as e:
        print("ERROR", e)
        duration = ''
    
    try:
        if get_hash:
            sha3_512_hash = hashlib.sha3_512()
            with open(temp_filename, 'rb') as f:
                while chunk := f.read(8192):
                    sha3_512_hash.update(chunk)
            sha3_512_checksum = f"""SHA3-512:{sha3_512_hash.hexdigest()}"""
        else:
            sha3_512_checksum = None
    except Exception:
        sha3_512_checksum = None
    
    return duration, sha3_512_checksum, temp_filename


def list_files_in_gcs_bucket(client, bucket_name, folder_path):
    folder_path = os.path.join(folder_path, "media")
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=folder_path)
    return {blob.name.replace(f"{folder_path}/", ""): {'checksum': convert_base64_md5(blob.md5_hash)} for blob in blobs}

def download_file_from_drive(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk(num_retries=2)
    fh.seek(0)
    return fh

def upload_file_to_gcs(client, bucket_name, blob_name, file_data, content_type):
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.chunk_size = 5 * 1024 * 1024  # chunk size 5 MB
    blob.upload_from_file(file_data, content_type=content_type, timeout=1200, rewind=True, retry=RETRY_POLICY)


def rsync_gdrive_and_other_storages(service_account_path, top_level_drive_folder, gcs_bucket_name, top_level_gcs_folder, sheet_id, worksheet_name, authenticated_url_prefix, project_name, lucid_storage, trint_storage, trint_workspace, trint_folder, is_shared_drive=True):
    creds = service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    with open("../vi-config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    gsheet_client = gspread.authorize(creds)
    spreadsheet = gsheet_client.open_by_key(sheet_id)
    sheet = spreadsheet.worksheet(worksheet_name)
    
    while True:
        try:
            all_values = sheet.get_all_values()
            break
        except APIError:
            sleep(60)
    
    headers = all_values[0]
    
    folders = list_files_in_drive_folder(service, top_level_drive_folder)

    media_files = list_files_in_drive_folder(service, folders['media']['id'])
    # print("media_files")
    # pprint(media_files)

    client = storage.Client.from_service_account_json(service_account_path)

    gcs_files = list_files_in_gcs_bucket(client, gcs_bucket_name, top_level_gcs_folder)
    # print("gcs_files")
    # pprint(gcs_files)

    files_to_transfer = {name: details for name, details in media_files.items() if name not in gcs_files or gcs_files[name]['checksum'] != details['checksum']}

    print("files_to_transfer")
    pprint(files_to_transfer)
    
    ranges_and_values = []
    num_manually_uploaded = 0

    for file_name in files_to_transfer:
        file_id = files_to_transfer[file_name]['id']
        print(datetime.now(), f"Downloading {file_name}")
        file_data = download_file_from_drive(service, file_id)
        print(datetime.now(), f"Downloaded {file_name}")

        content_type = files_to_transfer[file_name]['mimeType']

        print(datetime.now(), f"Transferring {file_name}")
        
        row = None
        col = headers.index("Link For Codec")

        for i, values in enumerate(all_values):
            if values[headers.index("UAR")] == os.path.splitext(file_name)[0]:
                row = i
                break
        
        if row is None:
            # This means there is a file in Google Drive that isn't tracked on the spreadsheet
            print(datetime.now(), f"Found a manually uploaded file: {file_name}")

            while True:
                try:
                    # col_values is 1-indexed (I think)
                    print(len(sheet.col_values(1)), len(sheet.col_values(2)), len(sheet.col_values(4)), num_manually_uploaded)
                    row = max(len(sheet.col_values(1)), len(sheet.col_values(2)), len(sheet.col_values(4))) + num_manually_uploaded
                    break
                except APIError:
                    sleep(60)

            num_manually_uploaded += 1

            uar = create_uar(top_level_gcs_folder, row+1)
            new_filename = f"""{uar}{os.path.splitext(file_name)[1]}"""
            rename_request_metadata = {'name': new_filename}

            query_params = {
                "fileId": file_id,
                "body": rename_request_metadata,
                "fields": 'id, name'
            }
            if is_shared_drive:
                query_params.update({
                    "supportsAllDrives": True
                })

            updated_file = service.files().update(**query_params).execute()
            file_gdrive_link = f"""https://drive.google.com/file/d/{file_id}/view?usp=sharing"""
            duration, sha3_512_checksum, temp_filename = get_media_duration_and_sha3_512(uar, file_data, files_to_transfer[file_name]['mimeType'])

            thumbnail_link = files_to_transfer[file_name]['thumbnailLink']
            if thumbnail_link is None:
                thumbnail_link = ''
            else:
                thumbnail_link = f"""=IMAGE("{thumbnail_link}")"""

            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("UAR")+1)}""",
                                  "values": [[uar]]
                                 })
            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Media Number + Archive Status")+1)}""", 
                                  "values": [["Manually uploaded"]]
                                 })
            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Media Thumbnail")+1)}""", 
                                  "values": [[thumbnail_link]]
                                 })
            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Archived File Location(s)")+1)}""", 
                                  "values": [[file_gdrive_link]]
                                 })
            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Original Downloaded Filename(s)")+1)}""", 
                                  "values": [[file_name]]
                                 })
            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Hash")+1)}""", 
                                  "values": [[sha3_512_checksum]]
                                 })

            file_name = new_filename

            sheet.format(f"{row+1}:{row+1}", {
                "backgroundColor": MANUAL_UPL_HIGHLIGHT_COLOR
            })

        else:
            duration, _, temp_filename = get_media_duration_and_sha3_512(os.path.splitext(file_name)[0], file_data, files_to_transfer[file_name]['mimeType'], get_hash=False)

        
        ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Duration (HH:MM:SS.mmmmmm)")+1)}""", 
                                "values": [[duration]]
                                })
        
        ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, col+1)}""",
                                  "values": [[f"""{authenticated_url_prefix}/{top_level_gcs_folder}/media/{file_name}"""]]
                                 })
        
        upload_file_to_gcs(client, gcs_bucket_name, os.path.join(top_level_gcs_folder, 'media', file_name), file_data, content_type)

        # Trint
        if trint_storage:
            print(f'uploading {file_name=} to folder id {trint_folder} in the Trint workspace with id {trint_workspace} ')
            try:
                trint_request_headers = {
                    "accept": "application/json",
                    "api-key": config.get("configurations", {}).get("trint_storage", {}).get("trint_api_key", ""),
                    "content-type": content_type
                }
                params = {
                    "language": config.get("configurations", {}).get("trint_storage", {}).get("language", ""),
                    "filename": file_name,
                    "workspace-id": trint_workspace,
                    "folder-id": trint_folder,
                }

                trint_api_url = config.get("configurations", {}).get("trint_storage", {}).get("trint_api_url", "")
                response = requests.post(trint_api_url, headers=trint_request_headers, params=params, data=open(temp_filename, "rb"))
                response.raise_for_status()
                response = response.json()
            except requests.RequestException as e:
                print(f"Error uploading to Trint: {e}")

            print(f'uploadf: uploaded file {response["trintId"]} successfully in folder id {trint_folder} in the Trint workspace with id {trint_workspace} ')

            ranges_and_values.append({"range": f"""{gspread.utils.rowcol_to_a1(row+1, headers.index("Trint Link")+1)}""", 
                                    "values": [[f"""https://app.trint.com/editor/{response["trintId"]}"""]]
                                    })

        # Lucid
        if lucid_storage:
            try:
                print(f'Copying {file_name=} to Lucid folder "/media/filespace/VI/{project_name}/media" ')
                lucid_dir = f"""/media/filespace/VI/{project_name}/media/"""
                os.makedirs(lucid_dir, exist_ok=True)
                src_file_name = temp_filename
                dst_file_name = os.path.join(lucid_dir, file_name)
                shutil.copy2(src_file_name, dst_file_name)
                print(f'Copied {file_name=} to Lucid succesfully ')

            except Exception as e:
                print("ERROR", e)

        print(datetime.now(), f"Transferred {file_name}, deleting the temp file {temp_filename}")
        os.remove(temp_filename)

    while True:
        try:
            sheet.batch_update(ranges_and_values, value_input_option='USER_ENTERED')
            break
        except APIError:
            sleep(60)

    print(datetime.now(), f"Updated spreadsheet")

# service_account_path = "../secrets/service_account.json"
# top_level_drive_folder = "153ITZjrC4InICxO2F1i_USYkUFkNBBrD"
# gcs_bucket_name = "vi_workflow"
# top_level_gcs_folder = "vi_workflow_tests_part_3"
# sheet_id = "1AOjaCHgKUUmIl_KaJvAIjD9NhMnNMj25Fs_ubWI0x1Q"
# worksheet_name = "Media"

# authenticated_url_prefix = f"https://storage.cloud.google.com/{gcs_bucket_name}"
# authenticated_url_prefix = f"https://storage.cloud.google.com/{gcs_bucket_name}"

# rsync_gdrive_and_gcs(service_account_path, top_level_drive_folder, gcs_bucket_name, top_level_gcs_folder, sheet_id, worksheet_name, authenticated_url_prefix)
