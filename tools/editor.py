#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, redirect, render_template, request, url_for, flash

# ---- Paths (repo-relative) ----
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # allow `import build` from repo root

META_DIR = ROOT / "episodes_meta"
TRANSCRIPTS_DIR = ROOT / "transcripts"
RAW_DIR = ROOT / "raw_transcripts"
PROCESSED_RAW_DIR = ROOT / "processed_transcripts"
TEMPLATES_DIR = ROOT / "templates_editor"

# Import RSS loader + slug logic from build.py
import build  # noqa: E402

app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
app.secret_key = os.environ.get("LBH_EDITOR_SECRET", "dev-secret-change-me")


# -----------------------------
# Models / helpers
# -----------------------------

@dataclass
class Episode:
    title: str
    slug: str
    date: str
    description: str
    audio_url: str
    image: str
    permalink: str

    # computed paths
    meta_path: Path
    transcript_html_path: Path
    transcript_md_path: Path
    transcript_pdf_path: Path
    raw_txt_path: Path

    overrides: Dict[str, Any]


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_site() -> Dict[str, Any]:
    cfg = read_json(ROOT / "site_config.json")
    if cfg:
        return cfg

    return {
        "title": "LAST BEST HOPE",
        "tagline": "An explicitly political Babylon 5 podcast",
        "description": "Using Babylon 5 to process the rise of authoritarianism in the real world.",
        "apple_podcasts_url": "https://podcasts.apple.com/us/podcast/last-best-hope-an-explicitly-political-babylon-5-podcast/id1801636475?mt=2&ls=1",
        "spotify_url": "https://open.spotify.com/show/5ASOLdJDYx8sLbwVZtiujd?si=ae23a5323ecb4906",
        "rss_url": "https://pinecast.com/feed/last-best-hope",
        "youtube_url": "",
        "bluesky_base_url": "https://bsky.app/profile/lastbesthopeb5.bsky.social",
        "reddit_thread_base": "",
        "mastodon_base_url": "",
    }


def list_episodes(limit: int = 50) -> List[Episode]:
    eps_raw = build.load_episodes_from_rss(build.FEED_URL, limit=limit)

    episodes: List[Episode] = []
    for e in eps_raw:
        slug = e["slug"]
        meta_path = META_DIR / f"{slug}.json"
        overrides = read_json(meta_path)

        episodes.append(
            Episode(
                title=e.get("title", ""),
                slug=slug,
                date=e.get("date", ""),
                description=e.get("description", ""),
                audio_url=e.get("audio_url", ""),
                image=e.get("image", ""),
                permalink=e.get("permalink", ""),
                meta_path=meta_path,
                transcript_html_path=TRANSCRIPTS_DIR / f"{slug}.html",
                transcript_md_path=TRANSCRIPTS_DIR / f"{slug}.md",
                transcript_pdf_path=TRANSCRIPTS_DIR / f"{slug}.pdf",
                raw_txt_path=RAW_DIR / f"{slug}.txt",
                overrides=overrides,
            )
        )

    return episodes


def get_episode_map(limit: int = 200) -> Dict[str, Episode]:
    return {ep.slug: ep for ep in list_episodes(limit=limit)}


def merged_field(ep: Episode, key: str, default: str = "") -> str:
    val = ep.overrides.get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()

    if key == "description":
        return ep.description or default
    if key == "title":
        return ep.title or default

    return default


def transcript_status(ep: Episode) -> Dict[str, bool]:
    return {
        "raw": ep.raw_txt_path.exists(),
        "html": ep.transcript_html_path.exists(),
        "md": ep.transcript_md_path.exists(),
        "pdf": ep.transcript_pdf_path.exists(),
    }


def run_cmd(cmd: List[str]) -> str:
    """
    Run a command in the repo root and return combined stdout/stderr.
    IMPORTANT: Use sys.executable for Python calls so venv is respected.
    """
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.stdout


def ensure_dirs() -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_RAW_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def index():
    site = load_site()
    episodes = list_episodes(limit=50)

    rows = []
    for ep in episodes:
        rows.append(
            {
                "ep": ep,
                "title": merged_field(ep, "title"),
                "description": merged_field(ep, "description"),
                "has_meta": ep.meta_path.exists(),
                "t": transcript_status(ep),
            }
        )

    return render_template("index.html", site=site, rows=rows)


@app.get("/episode/<slug>")
def edit_episode(slug: str):
    site = load_site()
    episodes = get_episode_map()
    ep = episodes.get(slug)
    if not ep:
        flash("Episode not found in RSS. Did the slug change?", "error")
        return redirect(url_for("index"))

    data = ep.overrides.copy()
    data.setdefault("title", ep.title)
    data.setdefault("description", ep.description)
    data.setdefault("youtube_url", "")
    data.setdefault("apple_url", "")
    data.setdefault("spotify_url", "")
    data.setdefault("rss_url", site.get("rss_url", ""))
    data.setdefault("links", [])

    return render_template(
        "episode_edit.html",
        site=site,
        ep=ep,
        data=data,
        t=transcript_status(ep),
    )


@app.post("/episode/<slug>")
def save_episode(slug: str):
    episodes = get_episode_map()
    ep = episodes.get(slug)
    if not ep:
        flash("Episode not found in RSS. Not saved.", "error")
        return redirect(url_for("index"))

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    youtube_url = request.form.get("youtube_url", "").strip()
    apple_url = request.form.get("apple_url", "").strip()
    spotify_url = request.form.get("spotify_url", "").strip()

    links_blob = request.form.get("links_blob", "").strip()
    links: List[Dict[str, str]] = []
    if links_blob:
        for line in links_blob.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                label, url = [p.strip() for p in line.split("|", 1)]
            else:
                label, url = "Link", line
            if url:
                links.append({"label": label or "Link", "url": url})

    payload = {
        "title": title,
        "description": description,
        "youtube_url": youtube_url,
        "apple_url": apple_url,
        "spotify_url": spotify_url,
        "links": links,
    }

    write_json(ep.meta_path, payload)
    flash("Saved episode overrides.", "ok")
    return redirect(url_for("edit_episode", slug=slug))


@app.post("/upload-transcript")
def upload_transcript():
    """
    Upload ONE raw Descript TXT for ONE episode.

    The UI should send:
      - slug (required)
      - file (required)
    We save it as raw_transcripts/<slug>.txt regardless of uploaded filename.
    """
    ensure_dirs()

    slug = (request.form.get("slug") or "").strip()
    f = request.files.get("file")

    if not slug:
        flash("Missing episode slug (upload must be tied to an episode).", "error")
        return redirect(url_for("index"))

    episodes = get_episode_map()
    if slug not in episodes:
        flash("That slug is not in the RSS feed. Check the slug.", "error")
        return redirect(url_for("index"))

    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("episode", slug=slug))

    out_path = RAW_DIR / f"{slug}.txt"
    f.save(out_path)
    flash(f"Uploaded raw transcript to {out_path.relative_to(ROOT)}", "ok")
    return redirect(url_for("edit_episode", slug=slug))


@app.post("/clean-transcript")
def clean_transcript_one():
    """
    Clean ONE transcript for ONE episode:
      raw_transcripts/<slug>.txt  -> transcripts/<slug>.md/.html/(.pdf)
      then move raw to processed_transcripts/<slug>.txt

    Uses tools/clean_transcript.py (single-file mode).
    """
    ensure_dirs()

    slug = (request.form.get("slug") or "").strip()
    if not slug:
        flash("Missing episode slug.", "error")
        return redirect(url_for("index"))

    episodes = get_episode_map()
    ep = episodes.get(slug)
    if not ep:
        flash("Episode not found in RSS. Did the slug change?", "error")
        return redirect(url_for("index"))

    raw_path = ep.raw_txt_path
    if not raw_path.exists():
        flash(f"No raw transcript found at {raw_path.relative_to(ROOT)}", "error")
        return redirect(url_for("edit_episode", slug=slug))

    out_base = TRANSCRIPTS_DIR / slug
    cleaner = ROOT / "tools" / "clean_transcript.py"

    cmd = [sys.executable, str(cleaner), str(raw_path), str(out_base)]
    out = run_cmd(cmd)

    # Write log
    (ROOT / ".last_transcripts.log").write_text(out, encoding="utf-8")

    # Move raw transcript to processed (overwrite if exists)
    processed_path = PROCESSED_RAW_DIR / f"{slug}.txt"
    try:
        if processed_path.exists():
            processed_path.unlink()
        raw_path.replace(processed_path)
        out += f"\nMoved raw file to {processed_path}\n"
        (ROOT / ".last_transcripts.log").write_text(out, encoding="utf-8")
    except Exception as e:
        out += f"\nWARNING: Could not move raw transcript to processed_transcripts: {e}\n"
        (ROOT / ".last_transcripts.log").write_text(out, encoding="utf-8")

    flash("Transcript cleaned. Check log if something looks off.", "ok")
    return redirect(url_for("edit_episode", slug=slug))

@app.post("/episode/<slug>/upload-transcript")
def upload_transcript_for_episode(slug: str):
    episodes = {ep.slug: ep for ep in list_episodes(limit=200)}
    ep = episodes.get(slug)
    if not ep:
        flash("Episode not found in RSS. Upload canceled.", "error")
        return redirect(url_for("index"))

    f = request.files.get("file")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("edit_episode", slug=slug))

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Force the filename to be the episode slug (prevents mismatches)
    out_path = RAW_DIR / f"{slug}.txt"
    f.save(out_path)

    flash(f"Uploaded raw transcript to {out_path.relative_to(ROOT)}", "ok")
    return redirect(url_for("edit_episode", slug=slug))


@app.post("/episode/<slug>/clean-transcript")
def clean_transcript_for_episode(slug: str):
    episodes = {ep.slug: ep for ep in list_episodes(limit=200)}
    ep = episodes.get(slug)
    if not ep:
        flash("Episode not found in RSS. Clean canceled.", "error")
        return redirect(url_for("index"))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_RAW_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = RAW_DIR / f"{slug}.txt"
    if not raw_path.exists():
        flash(f"Missing raw transcript: {raw_path.relative_to(ROOT)}", "error")
        return redirect(url_for("edit_episode", slug=slug))

    out_base = TRANSCRIPTS_DIR / slug

    # Run your existing clean_transcript.py
    cmd = [sys.executable, str(ROOT / "tools" / "clean_transcript.py"), str(raw_path), str(out_base)]
    out = run_cmd(cmd)
    (ROOT / ".last_transcripts.log").write_text(out, encoding="utf-8")

    # Move raw into processed_transcripts/
    processed_dest = PROCESSED_RAW_DIR / raw_path.name
    try:
        raw_path.replace(processed_dest)
    except Exception:
        # non-fatal: leave it in place if move fails
        pass

    flash("Cleaned transcript for this episode. See transcript log if needed.", "ok")
    return redirect(url_for("edit_episode", slug=slug))

@app.post("/run-build")
def run_build():
    ensure_dirs()
    out = run_cmd([sys.executable, str(ROOT / "build.py")])
    (ROOT / ".last_build.log").write_text(out, encoding="utf-8")
    flash("Build finished. (See build log.)", "ok")
    return redirect(url_for("build_log"))


@app.get("/build-log")
def build_log():
    site = load_site()
    log_path = ROOT / ".last_build.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else "(no build log yet)"
    return render_template("build_log.html", site=site, log=log)


@app.get("/transcript-log")
def transcript_log():
    site = load_site()
    log_path = ROOT / ".last_transcripts.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else "(no transcript log yet)"
    return render_template("transcript_log.html", site=site, log=log)


@app.post("/publish")
def publish():
    """
    One-button publish:
      - git add -A
      - commit (if needed)
      - push
      - run build.py
    Writes a combined log to .last_publish.log
    """
    ensure_dirs()

    commit_msg = (request.form.get("message") or "Publish updates").strip()

    log = []
    log.append("==> git status (pre)")
    log.append(run_cmd(["git", "status", "--porcelain"]))

    log.append("==> git add -A")
    log.append(run_cmd(["git", "add", "-A"]))

    # If nothing to commit, skip commit
    status = run_cmd(["git", "status", "--porcelain"]).strip()
    if status:
        log.append("==> git commit")
        log.append(run_cmd(["git", "commit", "-m", commit_msg]))
    else:
        log.append("==> nothing to commit; skipping commit")

    log.append("==> git push")
    log.append(run_cmd(["git", "push"]))

    log.append("==> python build.py")
    log.append(run_cmd([sys.executable, str(ROOT / "build.py")]))

    out = "\n".join(log) + "\n"
    (ROOT / ".last_publish.log").write_text(out, encoding="utf-8")

    flash("Publish ran. Check publish log if needed.", "ok")
    return redirect(url_for("publish_log"))


@app.get("/publish-log")
def publish_log():
    site = load_site()
    log_path = ROOT / ".last_publish.log"
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else "(no publish log yet)"
    return render_template("build_log.html", site=site, log=log)


def main():
    ensure_dirs()
    app.run(host="127.0.0.1", port=5544, debug=True)


if __name__ == "__main__":
    main()
