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
    """
    Turn an episode title into a URL-safe slug.
    """
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "episode"


def load_episodes_from_rss(url: str, limit: int = 20):
    """
    Fetch episodes from the RSS feed and convert them into the dicts
    our templates already expect.
    """
    feed = feedparser.parse(url)

    episodes = []
    for entry in feed.entries[:limit]:
        # Title
        title = entry.get("title", "Untitled episode")

        # Date
        if getattr(entry, "published_parsed", None):
            date_str = strftime("%Y-%m-%d", entry.published_parsed)
        elif getattr(entry, "updated_parsed", None):
            date_str = strftime("%Y-%m-%d", entry.updated_parsed)
        else:
            date_str = entry.get("published", "") or entry.get("updated", "")

        # Audio URL (first enclosure, if any)
        audio_url = "#"
        enclosures = getattr(entry, "enclosures", []) or entry.get("enclosures", [])
        if enclosures:
            audio_url = enclosures[0].get("href", "#")

        # Description
        description = entry.get("summary", "") or entry.get("description", "")

        episodes.append(
            {
                "title": title,
                "slug": slugify(title),
                "date": date_str,
                "description": description,
                "image": "/static/placeholder.jpg",  # keep placeholder for now
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
            "description": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
        },
        {
            "title": "Another Word for Surrender (THE FALL OF NIGHT)",
            "slug": "another-word-for-surrender-the-fall-of-night",
            "date": "2025-03-19",
            "description": "John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
        },
    ]

    site = {
        "title": "Last Best Hope",
        "tagline": "An explicitly political Babylon 5 podcast",
        "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
    }

    # 👉 NEW: try RSS, fall back to hardcoded
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

