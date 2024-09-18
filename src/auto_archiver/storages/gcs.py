
from typing import IO
from google.cloud import storage
import os

from ..utils.misc import random_str
from ..core import Media
from ..storages import Storage
from ..enrichers import HashEnricher
from loguru import logger


NO_DUPLICATES_FOLDER = "no-dups/"
class GCSStorage(Storage):
    # name = "gcs_storage"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        
        self.gcs_storage_client = storage.Client.from_service_account_json(self.service_account)
        self.bucket = self.gcs_storage_client.bucket(self.bucket_name)

        self.random_no_duplicate = bool(self.random_no_duplicate)
        if self.random_no_duplicate:
            logger.warning("random_no_duplicate is set to True, this will override `path_generator`, `filename_generator` and `folder`.")

    @staticmethod
    def configs() -> dict:
        return dict(
            Storage.configs(),
            ** {
                "bucket_name": {"default": None, "help": "GCS bucket name"},
                "service_account": {"default": None, "help": "Google Cloud Service Account credentials file"},
                "random_no_duplicate": {"default": False, "help": f"if set, it will override `path_generator`, `filename_generator` and `folder`. It will check if the file already exists and if so it will not upload it again. Creates a new root folder path `{NO_DUPLICATES_FOLDER}`"},
                "private": {"default": False, "help": "if true GCS files will not be readable online"},
                "scopes": {"default": None, "help": "Permission scopes the GCS client needs"},
                "top_level_folder": {"default": None, "help": "Folder within the bucket to put media"},
                "cdn_url": {"default": None, "help": "Folder within the bucket to put media"}
            })

    def uploadf(self, file: IO[bytes], media: Media, **kwargs: dict) -> None:
        if not self.is_upload_needed(media): return True

        #determine public vs private here
        extra_args = kwargs.get("extra_args", {})
        # if not self.private and 'ACL' not in extra_args:
            # extra_args['ACL'] = 'public-read'

        if 'ContentType' not in extra_args:
            try:
                if media.mimetype:
                    extra_args['ContentType'] = media.mimetype
            except Exception as e:
                logger.warning(f"Unable to get mimetype for {media.key=}, error: {e}")

        
        _, ext = os.path.splitext(media.key)

        if "thumbnail" in media.get("id", ""):
            # filename = f"""{media.key[:media.key.rfind("/")]}_screenshots/{media.key[media.key.rfind("/")+1:]}"""
            filename = os.path.join("thumbnails", f"""{media.get("row")}_{media.get("uar")}_{media.get("id", "")}{ext}""")
        elif "html_metadata" in media.get("id", ""):
            # filename = media.key.replace("/", "_")
            filename = os.path.join("html_metadata", f"""{media.get("row")}_{media.get("uar")}{ext}""")
        elif "screenshot" in media.get("id", ""):
            # filename = media.key.replace("/", "_")
            filename = os.path.join("screenshots", f"""{media.get("row")}_{media.get("uar")}{ext}""")
        elif "media" in media.get("id", ""):
            # filename = media.key.replace("/", "_")
            filename = os.path.join("media", f"""{media.get("row")}_{media.get("uar")}{ext}""")

        destination_blob_name = os.path.join(self.top_level_folder, filename)
        blob = self.bucket.blob(destination_blob_name)
        
        blob.upload_from_file(file, content_type=media.mimetype)

        media.set("destination_blob_name", destination_blob_name)

        return True
    
    def is_upload_needed(self, media: Media) -> bool:
        return True
        if self.random_no_duplicate:
            # checks if a folder with the hash already exists, if so it skips the upload
            he = HashEnricher({"hash_enricher": {"algorithm": "SHA-256", "chunksize": 1.6e7}})
            hd = he.calculate_hash(media.filename)
            path = os.path.join(NO_DUPLICATES_FOLDER, hd[:24])

            if existing_key:=self.file_in_folder(path):
                media.key = existing_key
                media.set("previously archived", True)
                logger.debug(f"skipping upload of {media.filename} because it already exists in {media.key}")
                return False
            
            _, ext = os.path.splitext(media.key)
            media.key = os.path.join(path, f"{random_str(24)}{ext}")
        return True
    
    
    def file_in_folder(self, path:str) -> str:
        return False
        # checks if path exists and is not an empty folder
        if not path.endswith('/'):
            path = path + '/' 
        resp = self.s3.list_objects(Bucket=self.bucket, Prefix=path, Delimiter='/', MaxKeys=1)
        if 'Contents' in resp:
            return resp['Contents'][0]['Key']
        return False
    
    def get_cdn_url(self, media: Media) -> str:
        # Add error handling
        return self.cdn_url.format(bucket_name=self.bucket_name, 
                                   key=media.get("destination_blob_name", ""))
    
class GCSStorage1(GCSStorage, Storage):
    name = "gcs_storage_1"

class GCSStorage2(GCSStorage, Storage):
    name = "gcs_storage_2"