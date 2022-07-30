import argparse
import csv
import os
from configparser import ConfigParser
from dataclasses import dataclass, asdict
from pathlib import Path

import requests


BASE_API_URL = "https://www.googleapis.com/youtube/v3/"
SUBS_API_URL = os.path.join(BASE_API_URL, "subscriptions")
SEARCH_API_URL = os.path.join(BASE_API_URL, "search")


with open("env.ini") as f:
    cfg = ConfigParser()
    cfg.readfp(f)

API_KEY = cfg.get("DEFAULT", "API_KEY")
MY_CHANNEL = cfg.get("DEFAULT", "MY_CHANNEL")

SUBS_CACHE = Path.home() / "dev/metube/subs.csv"


@dataclass(frozen=True)
class Channel:
    id: str
    title: str
    thumbnail: str


def get_all_subs() -> list:
    params = {
        "channelId": MY_CHANNEL,
        "key": API_KEY,
        "part": "snippet",
    }

    subs = []
    while True:
        result = requests.get(SUBS_API_URL, params=params)
        resp = result.json()

        if result.status_code != requests.codes.ok:
            raise RuntimeError(f"Failed to load subs:\n{resp}")

        for it in resp["items"]:
            info = it["snippet"]
            subs.append(
                Channel(
                    id=info["resourceId"]["channelId"],
                    title=info["title"],
                    thumbnail=info["thumbnails"]["high"]["url"],
                )
            )

        if resp.get("nextPageToken"):
            params["pageToken"] = resp["nextPageToken"]
        else:
            break

    return subs


def get_recent_vid_ids(channel_id: str) -> list:
    params = {
        "channelId": channel_id,
        "key": API_KEY,
        "part": "id",
        "type": "video",
        "order": "date",
    }
    result = requests.get(SEARCH_API_URL, params=params)
    resp = result.json()

    if result.status_code != requests.codes.ok:
        raise RuntimeError(f"Failed to get recent videos:\n{resp}")

    return [it["id"]["videoId"] for it in resp["items"]]


def recache_subs():
    subs = get_all_subs()
    with open(SUBS_CACHE, "w") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "title", "thumbnail"])
        writer.writeheader()
        for s in subs:
            writer.writerow(asdict(s))

    return subs

def load_subs():
    with open(SUBS_CACHE) as f:
        reader = csv.DictReader(f)
        return [Channel(**row) for row in reader]


def get_videos(args):
    subs = load_subs()
    print(len(subs))

    vids = []
    for s in subs:
        vids.extend(get_recent_vid_ids(s.id))

    Path(args.out_file).expanduser().write_text("\n".join(vids))


def load_imgs(args):
    subs = load_subs()
    for s in subs:
        resp = requests.get(s.thumbnail)
        if not resp.status_code == requests.codes.ok:
            print("Error pulling image for", s.title)
            continue

        try:
            with open(args.media_dir / s.title / "poster.jpeg", "wb") as f:
                list(map(f.write, resp))
        except Exception:
            pass


def main(args):
    if args.reload_subs:
        recache_subs()

    args.func(args)
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser("MeTube")
    parser.add_argument("--reload-subs", action="store_true", help="Re-cache the list of subs")

    subp = parser.add_subparsers()
    vids = subp.add_parser("vids", help="Get recent videos from subscriptions")
    vids.add_argument(
        "--out-file", default="vids.txt", help="Output file with video ids to download"
    )
    vids.set_defaults(func=get_videos)

    imgs = subp.add_parser("imgs", help="Load images for channels")
    imgs.add_argument("media_dir", type=Path, help="Media library of channels")
    imgs.set_defaults(func=load_imgs)


    main(parser.parse_args())
