# build.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
TEMPLATES_DIR = ROOT / "templates"
DIST_DIR = ROOT / "dist"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render(template_name, context, out_path):
    template = env.get_template(template_name)
    html = template.render(**context)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

def main():
    print("==> Building Last Best Hope site (clean version)")
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    context = {
        "site": {
            "title": "Last Best Hope",
            "tagline": "An explicitly political Babylon 5 podcast",
            "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
        },
        "episodes": [],  # we’ll wire this up later
    }

    render("home.html", context, DIST_DIR / "index.html")

if __name__ == "__main__":
    main()

