from __future__ import annotations
from dataclasses import dataclass
from abc import abstractmethod
from ..core import Metadata, Media, Step


@dataclass
class ProjectDetail(Step):
    name: str = None

    def __init__(self, config: dict) -> None:
        # without this STEP.__init__ is not called
        super().__init__(config)

    def init(name: str, config: dict) -> ProjectDetail:
        # only for code typing
        return Step.init(name, config, ProjectDetail)
    
class ProjectName(ProjectDetail):
    name = "project_name"

    @staticmethod
    def configs() -> dict:
        return {
            "value": {"default": "noname", "help": "a name for this project, to be used as a prefix when naming media files"},
        }
    
class ProjectFormat(ProjectDetail):
    name = "project_format"

    @staticmethod
    def configs() -> dict:
        return {
            "value": {"default": "vi-gd-gcs-codec", "help": "Used to denote standard media storage configurations that the archiver can assume are the case"},
        }
    
class ProjectNamingConvention(ProjectDetail):
    name = "project_naming_convention"

    # options:
    # only_uar
    # prefix_and_uar
    # date_title

    @staticmethod
    def configs() -> dict:
        return {
            "value": {"default": "only_uar", "help": "How media files in this project will be named"},
        }