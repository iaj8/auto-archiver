import hashlib
from loguru import logger

from . import Enricher
from ..core import Metadata

from datetime import timedelta
import ffmpeg



class DurationEnricher(Enricher):
    """
    Calculates duration for Media instances that are videos or audio clips
    """
    name = "duration_enricher"

    def __init__(self, config: dict) -> None:
        # without this STEP.__init__ is not called
        super().__init__(config)
        self.chunksize = int(self.chunksize)

    @staticmethod
    def configs() -> dict:
        return {
            "chunksize": {"default": int(1.6e7), "help": "number of bytes to use when reading files in chunks (if this value is too large you will run out of RAM), default is 16MB"},
        }

    def enrich(self, to_enrich: Metadata) -> None:
        url = to_enrich.get_url()
        logger.debug(f"calculating durations for {url=} (if it is a video or audio clip)")

        for i, m in enumerate(to_enrich.media):
            if len(duration := self.calculate_duration(m.filename)):
                to_enrich.media[i].set("duration_str", duration)

    def calculate_duration(self, filename) -> str:
        try:
            probe = ffmpeg.probe(filename)
            duration = float(probe['format']['duration'])
            duration = f"""{str(timedelta(seconds=duration))}"""

        except Exception as e:
            print("DURATION ERROR", e)
            duration = ''

        return duration