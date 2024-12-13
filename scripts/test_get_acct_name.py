# TikTok - in link name
# Facebook - using yt-dlp metadata extraction
# Instagram - using yt-dlp metadata extraction (additional processing step)
# Fox News - unknown
# Vimeo - using yt-dlp metadata extraction
# Twitter - in link name
# VK - not possible
# YouTube - using yt-dlp metadata extraction
# Rumble - using yt-dlp metadata extraction

# https://www.instagram.com/p/DDG2hi_tIz-/
# 


import subprocess
import json

from urllib.parse import urlparse

from pprint import pprint

def extract_full_domain(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    # Remove 'www.' prefix if present
    domain = domain.lstrip('www.')
    return domain

def print_acct_metadata(video_url):

    # Run yt-dlp command
    result = subprocess.run(
        ["yt-dlp", "-J", video_url],
        capture_output=True,
        text=True
    )

    # Parse JSON output
    metadata = json.loads(result.stdout)
    print("uploader", metadata.get("uploader", "UNKNOWN"))
    print("uploader", metadata.get("uploader", "UNKNOWN"))
    print("uploader_id", metadata.get("uploader_id", "UNKNOWN"))
    print("uploader_url", metadata.get("uploader_url", "UNKNOWN"))
    print("channel", metadata.get("channel", "UNKNOWN"))
    print("channel_id", metadata.get("channel_id", "UNKNOWN"))
    print("channel_url", metadata.get("channel_url", "UNKNOWN"))
    print("channel_follower_count", metadata.get("channel_follower_count", "UNKNOWN"))
    print("channel_is_verified", metadata.get("channel_is_verified", "UNKNOWN"))
    print("channel_is_verified_artist", metadata.get("channel_is_verified_artist", "UNKNOWN"))

if __name__ == '__main__':
    print_acct_metadata("https://rumble.com/v5csb1t-live-president-trump-in-potterville-mi.html")

    # links = set()

    # for line in open("test_links.txt", "r").readlines():
    #     link = line.replace("\n", "")
    #     if link:
    #         links.add(extract_full_domain(link))

    # pprint(links)