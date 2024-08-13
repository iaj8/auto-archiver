from __future__ import annotations
from dataclasses import dataclass
import mimetypes, os, pathlib
from urllib.parse import quote
from loguru import logger
import json
import base64

from ..version import __version__
from ..core import Metadata, Media, ArchivingContext
from . import Formatter
from ..enrichers import HashEnricher
from ..utils.misc import random_str


@dataclass
class GSheetFormatter(Formatter):
    name = "gsheet_formatter"

    def __init__(self, config: dict) -> None:
        # without this STEP.__init__ is not called
        super().__init__(config)

    def format(self, item: Metadata) -> Media:
        return Media(_mimetype="text/html")