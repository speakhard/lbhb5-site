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
    """Remove HTML tags (keep only text)."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text)


def format_pretty_date(parsed, fallback: str = "") -> str:
    """Turn a feedparser time struct into 'March 11, 2025'."""
    if not parsed:
        return fallback
    try:
        dt = datetime(*parsed[:6])
        month = dt.strftime("%B")
        day = dt.day
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
    for key in ("itunes_subtitle", "subtitle"):
        val = getattr(entry, key, None) or entry.get(key)
        if val:
            return strip_html(val).strip()

    raw = entry.get("summary", "") or entry.get("description", "")
    text = strip_html(raw).strip()
    if not text:
        return ""

    for sep in [". ", " – ", " - ", "\n"]:
        if sep in text:
            head = text.split(sep)[0].strip()
            if head:
                return head + "…"

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
      - bluesky_embed_html (str)
    """
    path = EPISODES_META_DIR / f"{slug}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_JUMPGATE_SENTINEL = "__LBHB5_JUMPGATE__"


def normalize_description(text: str) -> str:
    """
    Produce *safe HTML* for episode.description:
      - Unescape entities from RSS/JSON (&quot; etc)
      - Preserve the Babylon 5 jumpgate marker "<*>" and render it as literal "<*>"
      - Escape everything else (to avoid accidental HTML injection)
      - Convert newlines into <br> line breaks for simple formatting
    """
    if not text:
        return ""

    # Unescape once so we can treat content consistently
    text = html_lib.unescape(text)

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Preserve "<*>" (it would otherwise be treated as a tag and/or get mangled)
    text = text.replace("<*>", _JUMPGATE_SENTINEL)

    # Strip trailing whitespace per-line, trim outer whitespace
    text = "\n".join([ln.rstrip() for ln in text.split("\n")]).strip()

    # Now escape everything (safe HTML), then put jumpgate back as literal text.
    # To show literal "<*>" in HTML, we need &lt;*&gt; in the source.
    text = html_lib.escape(text, quote=True)
    text = text.replace(_JUMPGATE_SENTINEL, "&lt;*&gt;")

    # Preserve blank lines as extra spacing:
    # Convert double newlines to <br><br>, singles to <br>
    text = text.replace("\n\n", "\n\n")  # just explicit
    parts = text.split("\n\n")
    parts = [p.replace("\n", "<br>\n") for p in parts]
    text = "<br>\n<br>\n".join(parts)

    return text


_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def sanitize_bluesky_embed_html(embed_html: str) -> str:
    """
    You’re loading the Bluesky embed script in base.html,
    so per-episode embed HTML should be the <blockquote> only.

    This:
      - removes <script ...>...</script>
      - trims whitespace
    """
    if not embed_html:
        return ""
    cleaned = _SCRIPT_TAG_RE.sub("", embed_html).strip()
    return cleaned


def load_episodes_from_rss(url: str, limit: int = 50):
    feed = feedparser.parse(url)

    episodes = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "Untitled episode")

        published_struct = getattr(entry, "published_parsed", None)
        updated_struct = getattr(entry, "updated_parsed", None)

        if published_struct:
            date_str = format_pretty_date(published_struct)
        elif updated_struct:
            date_str = format_pretty_date(updated_struct)
        else:
            date_str = entry.get("published", "") or entry.get("updated", "")

        audio_url = "#"
        enclosures = getattr(entry, "enclosures", []) or entry.get("enclosures", [])
        if enclosures:
            audio_url = enclosures[0].get("href", "#")

        tagline = make_tagline(entry)

        raw_desc = entry.get("summary", "") or entry.get("description", "")
        # Strip any HTML tags from RSS, then normalize for safe HTML rendering
        full_description = normalize_description(strip_html(raw_desc).strip())

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
                "transcript_html": "",

                # per-episode overrides
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
    print("==> Building Last Best Hope site")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    copy_static()

    fallback_episodes = [
        {
            "title": "Nothing's the Same Anymore (CHRYSALIS)",
            "slug": "nothings-the-same-anymore-chrysalis",
            "date": "March 11, 2025",
            "tagline": "Josh and John discuss the season finale of Babylon 5's first season, after which everything changed.",
            "description": normalize_description("Josh and John discuss the season finale of Babylon 5's first season, after which everything changed."),
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
            "description": normalize_description("John and Josh discuss the parallels between Earth/Centauri/Narn and U.S./Russia/Ukraine."),
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

        "apple_podcasts_url": "https://podcasts.apple.com/us/podcast/last-best-hope-an-explicitly-political-babylon-5-podcast/id1801636475?mt=2&ls=1",
        "spotify_url": "https://open.spotify.com/show/5ASOLdJDYx8sLbwVZtiujd?si=ae23a5323ecb4906",
        "rss_url": FEED_URL,

        "bluesky_base_url": "https://bsky.app/profile/lastbesthopeb5.bsky.social",
        # "mastodon_base_url": "https://mastodon.instance/@LastBestHopeB5",
        # "reddit_thread_base": "https://www.reddit.com/r/LastBestHopeB5/",
    }

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

        if overrides.get("title"):
            ep["title"] = str(overrides["title"]).strip()

        if overrides.get("description"):
            # normalize into safe HTML (preserve "<*>", convert newlines to <br>, etc)
            ep["description"] = normalize_description(str(overrides["description"]))

        if isinstance(overrides.get("links"), list):
            ep["links"] = [
                {
                    "label": (l.get("label") or "").strip(),
                    "url": (l.get("url") or "").strip(),
                }
                for l in overrides["links"]
                if isinstance(l, dict) and (l.get("label") or l.get("url"))
            ]

        if overrides.get("bluesky_embed_html"):
            ep["bluesky_embed_html"] = sanitize_bluesky_embed_html(
                str(overrides["bluesky_embed_html"])
            )

        for k in ("youtube_url", "apple_url", "spotify_url"):
            if overrides.get(k):
                ep[k] = str(overrides[k]).strip()

    context = {"site": site, "episodes": episodes}

    # ---- Attach transcripts and copy transcript assets if available ----
    transcripts_out_dir = DIST_DIR / "transcripts"
    transcripts_out_dir.mkdir(parents=True, exist_ok=True)

    for ep in episodes:
        slug = ep["slug"]

        html_src = TRANSCRIPTS_DIR / f"{slug}.html"
        if html_src.exists():
            html_text = html_src.read_text(encoding="utf-8")
            ep["transcript_html"] = html_text
            shutil.copy2(html_src, transcripts_out_dir / f"{slug}.html")
        else:
            ep["transcript_html"] = ""

        for ext in ("md", "pdf"):
            src = TRANSCRIPTS_DIR / f"{slug}.{ext}"
            if src.exists():
                shutil.copy2(src, transcripts_out_dir / f"{slug}.{ext}")

    render("home.html", context, DIST_DIR / "index.html")
    render("episodes_index.html", context, DIST_DIR / "episodes" / "index.html")

    for ep in episodes:
        render(
            "episode.html",
            {"site": site, "episode": ep},
            DIST_DIR / "episodes" / f"{ep['slug']}.html",
        )


if __name__ == "__main__":
    main()
