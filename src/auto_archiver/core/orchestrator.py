from __future__ import annotations
from typing import Generator, Union, List
from urllib.parse import urlparse
from ipaddress import ip_address

from .context import ArchivingContext

from ..archivers import Archiver
from ..feeders import Feeder
from ..formatters import Formatter
from ..storages import Storage
from ..enrichers import Enricher
from ..databases import Database
from .metadata import Metadata

from .project_details import ProjectDetail

import tempfile, traceback
from loguru import logger

import random
import string


class ArchivingOrchestrator:
    def __init__(self, config) -> None:
        self.feeder: Feeder = config.feeder
        self.formatter: Formatter = config.formatter
        self.enrichers: List[Enricher] = config.enrichers
        self.archivers: List[Archiver] = config.archivers
        self.databases: List[Database] = config.databases
        self.storages: List[Storage] = config.storages
        self.thumbnail_storages: List[Storage] = config.thumbnail_storages
        self.html_metadata_storages: List[Storage] = config.html_metadata_storages
        self.screenshot_storages: List[Storage] = config.screenshot_storages
        self.project_details: List[ProjectDetail] = config.project_details

        ArchivingContext.set("storages", self.storages, keep_on_reset=True)
        ArchivingContext.set("thumbnail_storages", self.thumbnail_storages, keep_on_reset=True)
        ArchivingContext.set("html_metadata_storages", self.html_metadata_storages, keep_on_reset=True)
        ArchivingContext.set("screenshot_storages", self.screenshot_storages, keep_on_reset=True)
        ArchivingContext.set("project_details", self.project_details, keep_on_reset=True)

        try: 
            for a in self.all_archivers_for_setup(): a.setup()
        except (KeyboardInterrupt, Exception) as e:
            logger.error(f"Error during setup of archivers: {e}\n{traceback.format_exc()}")
            self.cleanup()


    def set_uar(self):
        project_name = None
        for detail in self.project_details:
            if detail.name == "project_name":
                project_name = detail.value

        if project_name is None:
            raise AssertionError("Project name should never be None. Check your config file")

        random_string = ''.join(random.choices(string.ascii_lowercase, k=2))

        return f"""{project_name}_{random_string}"""

    def cleanup(self)->None:
        logger.info("Cleaning up")
        for a in self.all_archivers_for_setup(): a.cleanup()

    def feed(self) -> Generator[Metadata]:
        for item in self.feeder:
            yield self.feed_item(item)
        self.cleanup()

    def feed_item(self, item: Metadata) -> Metadata:
        """
        Takes one item (URL) to archive and calls self.archive, additionally:
            - catches keyboard interruptions to do a clean exit
            - catches any unexpected error, logs it, and does a clean exit
        """
        try:
            ArchivingContext.reset()
            with tempfile.TemporaryDirectory(dir="./") as tmp_dir:
                ArchivingContext.set_tmp_dir(tmp_dir)
                return self.archive(item)
        except KeyboardInterrupt:
            # catches keyboard interruptions to do a clean exit
            logger.warning(f"caught interrupt on {item=}")
            for d in self.databases: d.aborted(item)
            self.cleanup()
            exit()
        except Exception as e:
            logger.error(f'Got unexpected error on item {item}: {e}\n{traceback.format_exc()}')
            for d in self.databases:
                if type(e) == AssertionError: d.failed(item, str(e))
                else: d.failed(item)


    def archive(self, result: Metadata) -> Union[Metadata, None]:
        """
            Runs the archiving process for a single URL
            1. Each archiver can sanitize its own URLs
            2. Check for cached results in Databases, and signal start to the databases
            3. Call Archivers until one succeeds
            4. Call Enrichers
            5. Store all downloaded/generated media
            6. Call selected Formatter and store formatted if needed
        """
        original_url = result.get_url().strip()
        self.assert_valid_url(original_url)

        # 1 - sanitize - each archiver is responsible for cleaning/expanding its own URLs
        url = original_url
        for a in self.archivers: url = a.sanitize_url(url)
        result.set_url(url)
        if original_url != url: result.set("original_url", original_url)

        # 2 - notify start to DBs, propagate already archived if feature enabled in DBs
        cached_result = None
        for d in self.databases:
            d.started(result)
            if (local_result := d.fetch(result)):
                cached_result = (cached_result or Metadata()).merge(local_result)
        if cached_result:
            logger.debug("Found previously archived entry")
            for d in self.databases:
                try: d.done(cached_result, cached=True)
                except Exception as e:
                    logger.error(f"ERROR database {d.name}: {e}: {traceback.format_exc()}")
            return cached_result

        # 3 - call archivers until one succeeds
        for a in self.archivers:
            logger.info(f"Trying archiver {a.name} for {url}")
            try:
                r = a.download(result)
                result.merge(r)
                if result.is_success() and result.get("credit_string") is not None: break
                elif result.is_success() and result.get("credit_string") is None:
                    logger.info("Getting just credits from youtubedl_archiver")
                    for archiver in self.archivers:
                        if archiver.name == "youtubedl_archiver":
                            archiver.download(result, only_credit_string=True)
            except Exception as e: 
                logger.error(f"ERROR archiver {a.name}: {e}: {traceback.format_exc()}")

        for i, m in enumerate(result.get_all_media()):
            m.set("id", f"""media_{i+1}""")

        # 4 - call enrichers to work with archived content
        for e in self.enrichers:
            try: e.enrich(result)
            except Exception as exc: 
                logger.error(f"ERROR enricher {e.name}: {exc}: {traceback.format_exc()}")

        gsheet = ArchivingContext.get("gsheet")
        for m in result.get_all_media():
            m.set("name_prefix", gsheet.get("name_prefix"))
            m.set("row", gsheet.get("row"))
            m.set("uar", self.set_uar())
            m.set("title", result.get("title"))
            m.set("timestamp", result.get("timestamp"))
        # 5 - store all downloaded/generated media
        result.store()

        # 6 - format and store formatted if needed
        if (final_media := self.formatter.format(result)):
            final_media.set("row", gsheet.get("row"))
            final_media.set("uar", self.set_uar())
            final_media.store(url=url, metadata=result)
            result.set_final_media(final_media)

        if result.is_empty():
            result.status = "nothing archived"

        # signal completion to databases and archivers
        for d in self.databases:
            try: d.done(result)
            except Exception as e:
                logger.error(f"ERROR database {d.name}: {e}: {traceback.format_exc()}")

        # set the row_offset to the number of links archived
        all_media = [m for m in result.get_all_media() if (m.get("id", "") != "_final_media" and "thumbnail" not in m.get("id", "") and "html_metadata" not in m.get("id", "") and "screenshot" not in m.get("id", ""))]
        self.feeder.row_offset = len(all_media)
        return result

    def assert_valid_url(self, url: str) -> bool:
        """
        Blocks localhost, private, reserved, and link-local IPs and all non-http/https schemes.
        """
        assert url.startswith("http://") or url.startswith("https://"), f"Invalid URL scheme"
        
        parsed = urlparse(url)
        assert parsed.scheme in ["http", "https"], f"Invalid URL scheme"
        assert parsed.hostname, f"Invalid URL hostname"
        assert parsed.hostname != "localhost", f"Invalid URL"

        try: # special rules for IP addresses
            ip = ip_address(parsed.hostname)
        except ValueError: pass
        else:
            assert ip.is_global, f"Invalid IP used"
            assert not ip.is_reserved, f"Invalid IP used"
            assert not ip.is_link_local, f"Invalid IP used"
            assert not ip.is_private, f"Invalid IP used"

    def all_archivers_for_setup(self) -> List[Archiver]:
        return self.archivers + [e for e in self.enrichers if isinstance(e, Archiver)]