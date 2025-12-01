from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

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

def main():
    print("==> Building Last Best Hope site (clean version)")
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    episodes = [
        {
            "title": "Who Are You? (Comes the Inquisitor)",
            "slug": "who-are-you",
            "date": "2025-01-01",
            "description": "Our manifesto and the political premise of the podcast.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#"
        },
        {
            "title": "Rules of Engagement (No Surrender, No Retreat)",
            "slug": "rules-of-engagement",
            "date": "2025-01-15",
            "description": "Exploring Earth’s slide into authoritarianism through the lens of Babylon 5.",
            "image": "/static/placeholder.jpg",
            "audio_url": "#"
        },
    ]

    site = {
        "title": "Last Best Hope",
        "tagline": "An explicitly political Babylon 5 podcast",
        "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
    }

    context = {
        "site": site,
        "episodes": episodes,
    }

    # Homepage
    render("home.html", context, DIST_DIR / "index.html")

    # Individual episode pages
    for ep in episodes:
        render(
            "episode.html",
            {"site": site, "episode": ep},
            DIST_DIR / "episodes" / f"{ep['slug']}.html"
        )

if __name__ == "__main__":
    main()

