import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import re
import feedparser
from time import strftime

ROOT = Path(__file__).parent
TEMPLATES_DIR = ROOT / "templates"
DIST_DIR = ROOT / "dist"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render(template_name, context, out_path: Path):
    template = env.get_template(template_name)
    html = template.render(**context)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


FEED_URL = "https://pinecast.com/feed/last-best-hope"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "episode"


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def make_tagline(entry):
    """
    Try to get a short tagline:
    1) explicit subtitle fields
    2) otherwise first sentence / ~180 chars of summary/description
    """
    # 1) subtitle fields if present
    for key in ("itunes_subtitle", "subtitle"):
        val = getattr(entry, key, None) or entry.get(key)
        if val:
            return strip_html(val).strip()

    # 2) fall back to summary/description
    raw = entry.get("summary", "") or entry.get("description", "")
    text = strip_html(raw).strip()
    if not text:
        return ""

    # try to cut at end of first sentence-ish
    for sep in [". ", " – ", " - ", "\n"]:
        if sep in text:
            head = text.split(sep)[0].strip()
            if head:
                return head + "…"

    # final fallback: truncate
    return text[:180].rstrip() + ("…" if len(text) > 180 else "")


def load_episodes_from_rss(url: str, limit: int = 50):
    feed = feedparser.parse(url)

    episodes = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "Untitled episode")

        # Date
        if getattr(entry, "published_parsed", None):
            date_str = strftime("%Y-%m-%d", entry.published_parsed)
        elif getattr(entry, "updated_parsed", None):
            date_str = strftime("%Y-%m-%d", entry.updated_parsed)
        else:
            date_str = entry.get("published", "") or entry.get("updated", "")

        # Audio URL
        audio_url = "#"
        enclosures = getattr(entry, "enclosures", []) or entry.get("enclosures", [])
        if enclosures:
            audio_url = enclosures[0].get("href", "#")

        # Tagline + full description
        tagline = make_tagline(entry)
        raw_desc = entry.get("summary", "") or entry.get("description", "")
        full_description = strip_html(raw_desc).strip()

        # Episode artwork
        image_url = None
        if getattr(entry, "itunes_image", None):
            image_url = entry.itunes_image
        elif isinstance(entry.get("image"), dict) and entry["image"].get("href"):
            image_url = entry["image"]["href"]
        elif entry.get("image"):
            image_url = entry["image"]

        if not image_url:
            image_url = "/static/placeholder.jpg"

        episodes.append(
            {
                "title": title,
                "slug": slugify(title),
                "date": date_str,
                "tagline": tagline,
                "description": full_description,
                "image": image_url,
                "audio_url": audio_url,
            }
        )

    return episodes


def copy_static():
    src = ROOT / "static"
    dest = DIST_DIR / "static"
    if src.exists():
        shutil.copytree(src, dest, dirs_exist_ok=True)


def main():
    print("==> Building Last Best Hope site (clean version)")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    copy_static()

    fallback_episodes = [
        {
            "title": "Nothing's the Same Anymore (CHRYSALIS)",
            "slug": "nothings-the-same-anymore-chrysalis",
            "date": "2025-03-11",
            "tagline": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "description": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
        },
        {
            "title": "Another Word for Surrender (THE FALL OF NIGHT)",
            "slug": "another-word-for-surrender-the-fall-of-night",
            "date": "2025-03-19",
            "tagline": "John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine.",
            "description": "John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
        },
    ]

    site = {
        "title": "Last Best Hope",
        "tagline": "An explicitly political Babylon 5 podcast",
        "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
        "feed_url": FEED_URL,
    }

    # Try RSS, fall back to hardcoded
    try:
        episodes = load_episodes_from_rss(FEED_URL, limit=20)
        if not episodes:
            raise ValueError("No episodes found in feed")
        print(f"Loaded {len(episodes)} episodes from RSS")
    except Exception as e:
        print(f"RSS fetch failed ({e}); using fallback episodes")
        episodes = fallback_episodes

    context = {
        "site": site,
        "episodes": episodes,
    }

    # Homepage
    render("home.html", context, DIST_DIR / "index.html")

    # Episodes index page
    render("episodes_index.html", context, DIST_DIR / "episodes" / "index.html")

    # Individual episode pages
    for ep in episodes:
        render(
            "episode.html",
            {"site": site, "episode": ep},
            DIST_DIR / "episodes" / f"{ep['slug']}.html",
        )


if __name__ == "__main__":
    main()
