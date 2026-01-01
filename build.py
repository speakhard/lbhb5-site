import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import re
import feedparser
from datetime import datetime
import json
import html as html_lib

ROOT = Path(__file__).parent
TEMPLATES_DIR = ROOT / "templates"
DIST_DIR = ROOT / "dist"
TRANSCRIPTS_DIR = ROOT / "transcripts"
EPISODES_META_DIR = ROOT / "episodes_meta"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

FEED_URL = "https://pinecast.com/feed/last-best-hope"


def render(template_name, context, out_path: Path):
    template = env.get_template(template_name)
    html = template.render(**context)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "episode"


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def format_pretty_date(parsed, fallback: str = "") -> str:
    """
    Turn a feedparser time struct into 'March 11, 2025'.
    If anything goes wrong, fall back to the provided string.
    """
    if not parsed:
        return fallback
    try:
        dt = datetime(*parsed[:6])
        month = dt.strftime("%B")  # 'March'
        day = dt.day               # 1–31, no leading zero
        year = dt.year
        return f"{month} {day}, {year}"
    except Exception:
        return fallback


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


def read_episode_overrides(slug: str) -> dict:
    """
    Read episodes_meta/<slug>.json if present.
    Expected keys (all optional):
      - title (str)
      - description (str)
      - youtube_url (str)
      - apple_url (str)
      - spotify_url (str)
      - links (list of {label,url})
      - bluesky_embed_html (str)  # full embed block + script
    """
    path = EPISODES_META_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_description(text: str) -> str:
    """
    Fix RSS/JSON description weirdness:
      - unescape HTML entities (&quot; etc)
      - normalize line endings
      - drop placeholder markers like <*>
      - keep paragraphs (convert newlines to <br> for simple rendering)
    """
    if not text:
        return ""

    # If RSS provided HTML-escaped content, unescape it.
    text = html_lib.unescape(text)

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove the specific placeholder marker you've been seeing
    text = text.replace("<*>", "").replace("< * >", "")

    # Trim trailing whitespace lines
    text = "\n".join([ln.rstrip() for ln in text.split("\n")]).strip()

    # Convert newlines to <br> for HTML rendering (since we strip HTML elsewhere)
    text = text.replace("\n\n", "\n")  # collapse double blank lines
    text = text.replace("\n", "<br>\n")

    return text


def load_episodes_from_rss(url: str, limit: int = 50):
    feed = feedparser.parse(url)

    episodes = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "Untitled episode")

        # Date
        published_struct = getattr(entry, "published_parsed", None)
        updated_struct = getattr(entry, "updated_parsed", None)

        if published_struct:
            date_str = format_pretty_date(published_struct)
        elif updated_struct:
            date_str = format_pretty_date(updated_struct)
        else:
            # fallback: raw string if no parsed struct exists
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
        full_description = normalize_description(full_description)

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

        slug = slugify(title)
        print(f"[EPISODE] {title} -> {slug}")

        episodes.append(
            {
                "title": title,
                "slug": slug,
                "date": date_str,
                "tagline": tagline,
                "description": full_description,
                "image": image_url,
                "audio_url": audio_url,
                "permalink": entry.get("link", ""),
                "transcript_html": "",  # will be filled in later if we have a file

                # per-episode overrides (filled in later)
                "links": [],
                "bluesky_embed_html": "",
                "youtube_url": "",
                "apple_url": "",
                "spotify_url": "",
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
            "date": "March 11, 2025",
            "tagline": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "description": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
            "permalink": "",
            "transcript_html": "",
            "links": [],
            "bluesky_embed_html": "",
            "youtube_url": "",
            "apple_url": "",
            "spotify_url": "",
        },
        {
            "title": "Another Word for Surrender (THE FALL OF NIGHT)",
            "slug": "another-word-for-surrender-the-fall-of-night",
            "date": "March 19, 2025",
            "tagline": "John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine.",
            "description": "John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#",
            "permalink": "",
            "transcript_html": "",
            "links": [],
            "bluesky_embed_html": "",
            "youtube_url": "",
            "apple_url": "",
            "spotify_url": "",
        },
    ]

    site = {
        "title": "LAST BEST HOPE",
        "tagline": "An explicitly political Babylon 5 podcast",
        "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
        "feed_url": FEED_URL,

        # Show-level platform URLs
        "apple_podcasts_url": "https://podcasts.apple.com/us/podcast/last-best-hope-an-explicitly-political-babylon-5-podcast/id1801636475?mt=2&ls=1",
        "spotify_url": "https://open.spotify.com/show/5ASOLdJDYx8sLbwVZtiujd?si=ae23a5323ecb4906",
        "rss_url": FEED_URL,
        # "youtube_url": "https://www.youtube.com/@YourChannelHere",

        # Discussion homes (optional but recommended)
        "bluesky_base_url": "https://bsky.app/profile/lastbesthopeb5.bsky.social",
        # "mastodon_base_url": "https://mastodon.instance/@LastBestHopeB5",
        # "reddit_thread_base": "https://www.reddit.com/r/LastBestHopeB5/",
    }

    # Try RSS, fall back to hardcoded
    try:
        episodes = load_episodes_from_rss(FEED_URL, limit=50)
        if not episodes:
            raise ValueError("No episodes found in feed")
        print(f"Loaded {len(episodes)} episodes from RSS")
    except Exception as e:
        print(f"RSS fetch failed ({e}); using fallback episodes")
        episodes = fallback_episodes

    # ---- Apply per-episode overrides from episodes_meta/<slug>.json ----
    for ep in episodes:
        overrides = read_episode_overrides(ep["slug"])

        # Allow title/description overrides (editor-written)
        if overrides.get("title"):
            ep["title"] = overrides["title"].strip()

        if overrides.get("description"):
            ep["description"] = normalize_description(overrides["description"])

        # Links & References (list of {label,url})
        if isinstance(overrides.get("links"), list):
            ep["links"] = [
                {"label": (l.get("label") or "").strip(), "url": (l.get("url") or "").strip()}
                for l in overrides["links"]
                if isinstance(l, dict) and (l.get("label") or l.get("url"))
            ]

        # Bluesky embed HTML (store the full blockquote+script)
        if overrides.get("bluesky_embed_html"):
            ep["bluesky_embed_html"] = overrides["bluesky_embed_html"]

        # Optional per-episode platform links if you want them later
        for k in ("youtube_url", "apple_url", "spotify_url"):
            if overrides.get(k):
                ep[k] = overrides[k].strip()

    context = {
        "site": site,
        "episodes": episodes,
    }

    # ---- Attach transcripts and copy transcript assets if available ----
    transcripts_out_dir = DIST_DIR / "transcripts"
    transcripts_out_dir.mkdir(parents=True, exist_ok=True)

    for ep in episodes:
        slug = ep["slug"]

        # HTML transcript for in-page panel + full-page view
        html_src = TRANSCRIPTS_DIR / f"{slug}.html"
        if html_src.exists():
            html_text = html_src.read_text(encoding="utf-8")
            ep["transcript_html"] = html_text

            # copy to dist/transcripts/<slug>.html for "open full transcript"
            html_dest = transcripts_out_dir / f"{slug}.html"
            shutil.copy2(html_src, html_dest)
        else:
            ep["transcript_html"] = ""

        # Optional Markdown / PDF downloads
        for ext in ("md", "pdf"):
            src = TRANSCRIPTS_DIR / f"{slug}.{ext}"
            if src.exists():
                dest = transcripts_out_dir / f"{slug}.{ext}"
                shutil.copy2(src, dest)

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
