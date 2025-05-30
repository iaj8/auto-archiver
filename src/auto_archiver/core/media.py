
from __future__ import annotations
import os
import traceback
from typing import Any, List
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config
import mimetypes

import ffmpeg
from ffmpeg._run import Error

from .context import ArchivingContext

from loguru import logger

import re
from urllib.parse import urlparse


@dataclass_json  # annotation order matters
@dataclass
class Media:
    filename: str
    key: str = None
    urls: List[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    _mimetype: str = None  # eg: image/jpeg
    _stored: bool = field(default=False, repr=False, metadata=config(exclude=lambda _: True))  # always exclude

    domain_to_website_name = {
        'foxnews.com': 'Fox News',
        't.me': 'Telegram',
        'x.com': 'X',
        'youtube.com': 'YouTube',
        'youtu.be': 'YouTube',
        'facebook.com': 'Facebook',
        'bsky.app': 'Bluesky',
        'c-span.org': 'C-SPAN',
        'instagram.com': 'Instagram',
        'mobile.x.com': 'X',
        'player.vimeo.com': 'Vimeo',
        'podcasts.apple.com': 'Apple Podcasts',
        'reddit.com': 'Reddit',
        'rumble.com': 'Rumble',
        'tiktok.com': 'TikTok',
        'twitter.com': 'X',
        'v.douyin.com': 'Douyin',
        'vimeo.com': 'Vimeo',
        'vk.com': 'VKontakte',
    }

    def store(self: Media, override_storages: List = None, url: str = "url-not-available", metadata: Any = None):
        # 'Any' typing for metadata to avoid circular imports. Stores the media
        # into the provided/available storages [Storage] repeats the process for
        # its properties, in case they have inner media themselves for now it
        # only goes down 1 level but it's easy to make it recursive if needed.
        storages = override_storages or ArchivingContext.get("storages")
        thumbnail_storages = ArchivingContext.get("thumbnail_storages")
        html_metadata_storages = ArchivingContext.get("html_metadata_storages")
        screenshot_storages = ArchivingContext.get("screenshot_storages")

        if not len(storages):
            logger.warning(f"No storages found in local context or provided directly for {self.filename}.")
            return

        for s in storages:
            for any_media in self.all_inner_media(include_self=True):
                # if its not a thumbnail and its not a metadata file
                if any_media.get("id") is None or ("thumbnail" not in any_media.get("id") 
                    and "html_metadata" not in any_media.get("id")
                    and "screenshot" not in any_media.get("id")
                ):
                    s.store(any_media, url, metadata=metadata)

        for s in thumbnail_storages:
            for any_media in self.all_inner_media(include_self=True):
                # if it is a thumbnail
                if any_media.get("id") is not None and "thumbnail" in any_media.get("id"):
                    s.store(any_media, url, metadata=metadata)

        for s in html_metadata_storages:
            for any_media in self.all_inner_media(include_self=True):
                # if it is a metadata file
                if any_media.get("id") is not None and "html_metadata" in any_media.get("id"):
                    s.store(any_media, url, metadata=metadata)

        for s in screenshot_storages:
            for any_media in self.all_inner_media(include_self=True):
                # if it is a metadata file
                if any_media.get("id") is not None and "screenshot" in any_media.get("id"):
                    s.store(any_media, url, metadata=metadata)

    def all_inner_media(self, include_self=False):
        """ Media can be inside media properties, examples include transformations on original media.
        This function returns a generator for all the inner media.        
        """
        if include_self: yield self
        for prop in self.properties.values():
            if isinstance(prop, Media): 
                for inner_media in prop.all_inner_media(include_self=True):
                    yield inner_media
            if isinstance(prop, list):
                for prop_media in prop:
                    if isinstance(prop_media, Media): 
                        for inner_media in prop_media.all_inner_media(include_self=True):
                            yield inner_media

    def is_stored(self) -> bool:
        return len(self.urls) > 0 and len(self.urls) == len(ArchivingContext.get("storages"))

    def set(self, key: str, value: Any) -> Media:
        self.properties[key] = value
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)

    def add_url(self, url: str) -> None:
        # url can be remote, local, ...
        self.urls.append(url)

    @property  # getter .mimetype
    def mimetype(self) -> str:
        if not self.filename or len(self.filename) == 0:
            logger.warning(f"cannot get mimetype from media without filename: {self}")
            return ""
        if not self._mimetype:
            self._mimetype = mimetypes.guess_type(self.filename)[0]
        return self._mimetype or ""

    @mimetype.setter  # setter .mimetype
    def mimetype(self, v: str) -> None:
        self._mimetype = v

    def is_video(self) -> bool:
        return self.mimetype.startswith("video")

    def is_audio(self) -> bool:
        return self.mimetype.startswith("audio")

    def is_image(self) -> bool:
        return self.mimetype.startswith("image")

    def is_valid_video(self) -> bool:
        # checks for video streams with ffmpeg, or min file size for a video
        # self.is_video() should be used together with this method
        try:
            streams = ffmpeg.probe(self.filename, select_streams='v')['streams']
            logger.warning(f"STREAMS FOR {self.filename} {streams}")
            return any(s.get("duration_ts", 0) > 0 for s in streams)
        except Error: return False # ffmpeg errors when reading bad files
        except Exception as e:
            logger.error(e)
            logger.error(traceback.format_exc())
            try:
                fsize = os.path.getsize(self.filename)
                return fsize > 20_000
            except: pass
        return True
    
    def clean_string(self, input_string):

        input_string = input_string.strip()

        # Remove emojis using regex pattern for unicode characters in emoji ranges
        input_string = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251]', '', input_string)
        # Remove emojis, including additional ones like ❗‼️⁉️
        input_string = re.sub(
            r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
            r'\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF'
            r'\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
            r'\U00002702-\U000027B0\U000024C2-\U0001F251'
            r'\u203C\u2049\u2753-\u2755\u2757\u26A0\u26A1\u2B06-\u2B07\u2B50\u2B55]',
            '',
            input_string
        )

        input_string = input_string.replace("\u200d", "")

        # Remove basic punctuation
        input_string = re.sub(r'[!?,:;\'"{}\[\]@|•’‘#&™+]', '', input_string)

        input_string = input_string.replace("…", "...")
        input_string = input_string.replace("/", "_")
        
        # Replace spaces with underscores
        input_string = input_string.replace(" ", "_")

        return input_string

    @staticmethod
    def extract_full_domain(url):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Remove 'www.' prefix if present
        domain = domain.lstrip('www.')
        return domain
    
    @staticmethod
    def get_website_name(url):
        domain = Media.extract_full_domain(url)
        print("domain", domain)
        try:
            print("Media.domain_to_website_name[domain]", Media.domain_to_website_name[domain])
            return Media.domain_to_website_name[domain]
        except KeyError:
            return domain
