
import shutil, os, time, json
from typing import IO
from loguru import logger

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..core import Media
from . import Storage

import re

from datetime import datetime
import pytz

import requests


class TrintStorage(Storage):
    name = "trint_storage"
    est = pytz.timezone('US/Eastern')

    def __init__(self, config: dict) -> None:
        super().__init__(config)

    @staticmethod
    def configs() -> dict:
        return dict(
            Storage.configs(),
            ** {
                "trint_api_url": {"default": "https://upload.trint.com/", "help": "The endpoint to upload files for Trint transcription"},
                "trint_api_key": {"default": "bdd936526b797a6039da08877742ad7f025293ad", "help": "Trint API key"},
                "language": {"default": "en", "help":"Language to transcribe videos/audios in"},
                "workspace_id": {"default": "dlxkjmhkSHG_zE5ecKueAQ", "help": "The Trint workspace to upload files to for transcription"},
                "folder_id": {"default": "ZLUzlqpvRSeRI7GJ-cXJIg", "help": "The folder within the Trint workspace to upload files to for transcription"},
            })

    def get_cdn_url(self, media: Media) -> str:
        """
        URL of the file's interface on Trint
        """
        return f"""https://app.trint.com/editor/{media.get("file_trint_id")}"""

    def upload(self, media: Media, **kwargs) -> bool:
        logger.debug(f'[{self.__class__.name}] storing file {media.filename} with key {media.key}')
        """
        1. for each sub-folder in the path check if exists or create
        2. upload file to root_id/other_paths.../filename
        """
        workspace_id, folder_id = self.workspace_id, self.folder_id
        filename, mime_type = self.get_filename_and_mimetype(media)

        # upload file to gd
        logger.debug(f'uploading {filename=} to folder id {folder_id} in the Trint workspace with id {workspace_id} ')

        try:
            headers = {
                "accept": "application/json",
                "api-key": self.trint_api_key,
                "content-type": mime_type
            }
            params = {
                "language": self.language,
                "filename": filename,
                "workspace-id": workspace_id,
                "folder-id": folder_id,
            }

            fh = open(media.filename, "rb")
            response = requests.post(self.trint_api_url, headers=headers, params=params, data=fh)
            response.raise_for_status()
            response = response.json()
            media.set("file_trint_id", response["trintId"])
        except requests.RequestException as e:
            logger.debug(f"Error uploading to Trint: {e}")

        logger.debug(f'uploadf: uploaded file {response["trintId"]} successfully in folder id {folder_id} in the Trint workspace with id {workspace_id} ')

    # must be implemented even if unused
    def uploadf(self, file: IO[bytes], key: str, **kwargs: dict) -> bool: pass

    def get_filename_and_mimetype(self, media: Media):

        _, ext = os.path.splitext(media.key)

        if "media" in media.get("id"):
            i = int(re.search(r'\d+', media.get("id")).group()) - 1

            # timestamp = media.get("timestamp").astimezone(self.est).strftime("%Y-%m-%d")
            # title = media.get("title")

            # filename = f"""{timestamp} EST {title}_{media.get("row")+i}{ext}"""
            
            # filename = media.clean_string(filename)
            
            filename = f"""{media.get("row")+i}_{media.get("name_prefix")}_{media.get("uar")}{ext}"""

        else:

            filename = "NONE"
        
        return filename, media.mimetype