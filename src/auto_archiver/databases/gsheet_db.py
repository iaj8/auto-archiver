from typing import Union, Tuple
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from loguru import logger

from . import Database
from ..core import Metadata, Media, ArchivingContext
from ..utils import GWorksheet

import os

from google.cloud import translate_v2 as translate

import re
import random
import string

class GsheetsDb(Database):
    """
        NB: only works if GsheetFeeder is used. 
        could be updated in the future to support non-GsheetFeeder metadata 
    """
    name = "gsheet_db"

    def __init__(self, config: dict) -> None:
        # without this STEP.__init__ is not called
        super().__init__(config)
        self.translate_client = translate.Client.from_service_account_json(self.service_account)

    @staticmethod
    def configs() -> dict:
        return {
            "service_account": {"default": "secrets/service_account.json", "help": "service account JSON file path"},
        }

    def started(self, item: Metadata) -> None:
        logger.warning(f"STARTED {item}")
        gw, row = self._retrieve_gsheet(item)
        gw.set_cell(row, 'status', 'Archive in progress')

    def failed(self, item: Metadata, reason:str) -> None:
        logger.error(f"FAILED {item}")
        self._safe_status_update(item, f'Archive failed {reason}')

    def aborted(self, item: Metadata) -> None:
        logger.warning(f"ABORTED {item}")
        self._safe_status_update(item, '')

    def fetch(self, item: Metadata) -> Union[Metadata, bool]:
        """check if the given item has been archived already"""
        return False

    def done(self, item: Metadata, cached: bool=False) -> None:
        """archival result ready - should be saved to DB"""
        logger.success(f"DONE {item.get_url()}")
        gw, row = self._retrieve_gsheet(item)
        # self._safe_status_update(item, 'done')

        cell_updates = []
        row_values = gw.get_row(row)

        def batch_if_valid(offset_row, col, val, final_value=None):
            final_value = final_value or val
            try:
                if val and gw.col_exists(col) and gw.get_cell(row_values, col) == '':
                    if type(final_value) == str and len(final_value) > 5000:
                        final_value = f"""{final_value[:4800]}..."""
                    cell_updates.append((offset_row, col, final_value))
            except Exception as e:
                logger.error(f"Unable to batch {col}={final_value} due to {e}")

        status_message = item.status
        if cached:
            status_message = f"[cached] {status_message}"

        media: Media = item.get_final_media()
        if hasattr(media, "urls"):
            for i, media_url in enumerate(media.urls):
                batch_if_valid(row+i, 'archive', media_url)

        batch_if_valid(row, 'date', True, datetime.utcnow().replace(tzinfo=timezone.utc).isoformat())
        
        batch_if_valid(row, 'title', item.get_title())
        
        title_translated = self.translate_client.translate(item.get("title", ""), target_language='en')
        if title_translated["detectedSourceLanguage"] != 'en':
            batch_if_valid(row, 'title_translated', 
                f"""({title_translated["detectedSourceLanguage"]}) {title_translated["translatedText"]}""")

        edited_text = None
        if item.get("edited_text", None) is None:
            edited_text = item.get("content", "")
        else:
            edited_text = item.get("edited_text", "")

        batch_if_valid(row, 'text', edited_text)
        text_translated = self.translate_client.translate(edited_text, target_language='en')
        if text_translated["detectedSourceLanguage"] != 'en':
            batch_if_valid(row, 'text_translated', 
                f"""({text_translated["detectedSourceLanguage"]}) {text_translated["translatedText"]}""")
        
        timestamp = item.get_timestamp()
        if timestamp is not None:
            est = timezone(timedelta(hours=-5))
            date_utc = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S%z')
            date_est = date_utc.astimezone(est)

            batch_if_valid(row, 'timestamp', date_utc.strftime('%Y-%m-%d %I:%M:%S %p'))
            batch_if_valid(row, 'timestamp_est', date_est.strftime('%Y-%m-%d %I:%M:%S %p'))

        # merge all pdq hashes into a single string, if present
        pdq_hashes = []
        
        downloaded_filenames = []
        archived_filenames = []

        folder = None

        all_media = [m for m in item.get_all_media() if (m.get("id", "") != "_final_media" and "thumbnail" not in m.get("id", "") and "html_metadata" not in m.get("id", "") and "screenshot" not in m.get("id", ""))]
        if len(all_media) == 0:
            cell_updates.append((row, 'status', "no media or no archiver for this website"))
            try:
                batch_if_valid(row, 'uar', f"""{row}_{item.get_final_media().get("uar")}""")
            except AttributeError:
                random_string = ''.join(random.choices(string.ascii_lowercase, k=2))
                batch_if_valid(row, 'uar', f"""{row}_no_media_{random_string}""")

        for m in all_media:
            m: Media
            if pdq := m.get("pdq_hash"):
                pdq_hashes.append(pdq)

            i = int(re.search(r'\d+', m.get("id")).group()) - 1

            batch_if_valid(row+i, 'uar', f"""{row+i}_{m.get("uar")}""")
            
            batch_if_valid(row+i, 'credit_string', item.get("credit_string"))
        
            downloaded_filename = os.path.basename(m.filename)
            codec_filename = None
            project_format = None
            for detail in ArchivingContext.get("project_details"):
                if detail.name == "project_format":
                    project_format = detail.value

            if project_format is None:
                archived_filename = m.urls[0]
            elif project_format == "vi-gd-gcs-codec":
                for u in m.urls:
                    if "drive.google.com" in u:
                        archived_filename = u
                    if "storage.cloud.google" in u:
                        codec_filename = u
                    
            if codec_filename is not None:
                batch_if_valid(row+i, 'codec_link', codec_filename)

            batch_if_valid(row+i, 'downloaded_filenames', downloaded_filename)
            batch_if_valid(row+i, 'archived_filenames', archived_filename)

            # TODO: Make it so that if some fail but others succeed this is still accurate
            cell_updates.append((row+i, 'status', f"""{i+1}/{len(all_media)}: {status_message}"""))

            batch_if_valid(row+i, 'hash', m.get("hash", "not-calculated"))

            batch_if_valid(row, 'duration', m.get("duration_str", ""))

            try:
                # if hasattr(m, "thumbnails"): TODO: For some reason hasattr doesn't work here
                if m.get("thumbnails") is not None and m.get("thumbnails")[0] is not None:
                    batch_if_valid(row+i, 'thumbnail', f'=IMAGE("{m.get("thumbnails")[0].urls[0]}")')
                else:
                    batch_if_valid(row+i, 'thumbnail', f'=IMAGE("{m.urls[0]}")')
            except IndexError:
                batch_if_valid(row+i, 'thumbnail', f'=IMAGE("{m.urls[0]}")')

            # downloaded_filenames.append(downloaded_filename)
            # archived_filenames.append(archived_filename)

        # if m.get("id", "") == "_final_media":
        #     folder = m.urls[0].replace(m.key.replace("/", "_"), "")

        # if len(pdq_hashes):
        #     batch_if_valid('pdq_hash', "\n".join(pdq_hashes))

        # if len(downloaded_filenames):
        #     batch_if_valid('downloaded_filenames', "\n".join(downloaded_filenames))

        # if len(archived_filenames):
        #     batch_if_valid('archived_filenames', "\n".join(archived_filenames))

        # batch_if_valid('folder', folder)

        if (screenshot := item.get_media_by_id("screenshot")) and hasattr(screenshot, "urls"):
            batch_if_valid(row, 'screenshot', "\n".join(screenshot.urls))

        if (browsertrix := item.get_media_by_id("browsertrix")):
            batch_if_valid(row, 'wacz', "\n".join(browsertrix.urls))
            batch_if_valid(row, 'replaywebpage', "\n".join([f'https://replayweb.page/?source={quote(wacz)}#view=pages&url={quote(item.get_url())}' for wacz in browsertrix.urls]))


        batch_if_valid(row, 'credit_string', item.get("credit_string"))

        gw.batch_set_cell(cell_updates)

    def _safe_status_update(self, item: Metadata, new_status: str) -> None:
        try:
            gw, row = self._retrieve_gsheet(item)
            gw.set_cell(row, 'status', new_status)
        except Exception as e:
            logger.debug(f"Unable to update sheet: {e}")

    def _retrieve_gsheet(self, item: Metadata) -> Tuple[GWorksheet, int]:
        # TODO: to make gsheet_db less coupled with gsheet_feeder's "gsheet" parameter, this method could 1st try to fetch "gsheet" from ArchivingContext and, if missing, manage its own singleton - not needed for now
        if gsheet := ArchivingContext.get("gsheet"):
            gw: GWorksheet = gsheet.get("worksheet")
            row: int = gsheet.get("row")
        elif self.sheet_id:
            print(self.sheet_id)


        return gw, row
