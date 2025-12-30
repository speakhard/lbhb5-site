#!/usr/bin/env python3
"""
Babylon 5 podcast transcript cleaner.

Usage:
    python clean_transcript.py input.txt output_basename

This will create:
    output_basename.md
    output_basename.html
    (optionally) output_basename.pdf   if pandoc is installed
"""

import re
import sys
import subprocess
import shutil
from typing import List, Dict, Tuple, Optional
import html as html_lib

TC_RE = re.compile(r'^\[(\d{2}:\d{2}:\d{2})\]\s+([A-Z]+):\s*(.*)$')

def group_turns(lines: List[str]) -> Tuple[Optional[Dict], List[Dict]]:
    turns: List[Dict] = []
    current: Optional[Dict] = None

    for line in lines:
        m = TC_RE.match(line)
        if m:
            # start a new turn
            if current:
                turns.append(current)
            tc, spk, txt = m.groups()
            current = {"time": tc, "speaker": spk, "text": txt.strip()}
        else:
            # continuation of current turn or free text
            if current:
                s = line.strip()
                if s:
                    current["text"] += " " + s
            else:
                if line.strip():
                    turns.append({"time": None, "speaker": None, "text": line.strip()})

    if current:
        turns.append(current)

    # You *might* have a header or notes up top; keep it simple:
    header = None
    if turns and turns[0]["time"] is None:
        header = turns[0]
        turns = turns[1:]

    return header, turns


def clean_dialog(d: str) -> str:
    # Custom replacements
    d = d.replace("mapable", "mappable")
    d = d.replace("antia sentiment", "anti-alien sentiment")
    d = re.sub(r"\bThat's been\b", "It's been", d)

    # Filler cleanup
    d = re.sub(r'^\s*(Um|Uh)[\.,]?\s+', '', d, flags=re.I)
    d = re.sub(r'\b(um|uh)[\.,]?\b', '', d, flags=re.I)
    d = re.sub(r'\byou know,?\s*', '', d, flags=re.I)
    d = re.sub(r'\blike,\s+(?=(you|we|I|it|that)\b)', '', d, flags=re.I)

    d = re.sub(r'\s{2,}', ' ', d).strip()

    # Punctuation smoothing
    d = d.replace("—", ",")
    d = d.replace(":", ",")

    return d


def clean_turns(lines: List[str]) -> Tuple[Optional[Dict], List[Dict]]:
    header, turns = group_turns(lines)

    cleaned: List[Dict] = []
    for t in turns:
        if not t["time"]:
            cleaned.append(t)
        else:
            cleaned.append(
                {
                    "time": t["time"],
                    "speaker": t["speaker"],
                    "text": clean_dialog(t["text"]),
                }
            )
    return header, cleaned


# ---------- Markdown rendering ----------

def render_markdown(header: Optional[Dict], turns: List[Dict]) -> str:
    out: List[str] = []

    if header:
        out.append(header["text"])
        out.append("")

    for t in turns:
        if not t["time"]:
            out.append(t["text"])
        else:
            out.append(f"[{t['time']}] **{t['speaker']}**, {t['text']}")

    return "\n\n".join(out)


# ---------- HTML fragment rendering ----------

def escape(s: str) -> str:
    return html_lib.escape(s, quote=True)


def render_html_fragment(header: Optional[Dict], turns: List[Dict]) -> str:
    """
    Returns an HTML **fragment** (no <html> or <body>) that you can drop
    directly into your Jinja template via `episode.transcript_html`.

    Timestamps are wrapped in <span class="tc" data-tc="HH:MM:SS">[…]</span>
    so you can toggle them with CSS/JS.
    """
    lines: List[str] = []
    lines.append('<div class="transcript-body">')

    if header:
        lines.append(
            f'  <p class="transcript-preface">{escape(header["text"])}</p>'
        )

    for t in turns:
        if not t["time"]:
            lines.append(
                f'  <p class="transcript-note">{escape(t["text"])}</p>'
            )
        else:
            tc = escape(t["time"])
            speaker = escape(t["speaker"])
            text = escape(t["text"])
            lines.append(
                '  <p class="transcript-turn">'
                f'<span class="tc" data-tc="{tc}">[{tc}]</span> '
                f'<span class="speaker">{speaker}</span>, '
                f'<span class="line">{text}</span>'
                '</p>'
            )

    lines.append("</div>")
    return "\n".join(lines)


# ---------- Optional PDF generation via pandoc ----------

def write_pdf_from_markdown(md_path: str, pdf_path: str) -> None:
    """
    Uses `pandoc` if available. If not found, just skips PDF creation.
    """
    if shutil.which("pandoc") is None:
        print("pandoc not found; skipping PDF for", md_path)
        return

    try:
        subprocess.run(
            ["pandoc", md_path, "-o", pdf_path],
            check=True,
        )
        print("Wrote PDF:", pdf_path)
    except subprocess.CalledProcessError as e:
        print("pandoc failed, skipping PDF:", e)


# ---------- Top-level clean function ----------

def clean_transcript(input_path: str, output_base: str):
    with open(input_path, encoding="utf-8") as f:
        raw = f.read()

    lines = raw.splitlines()
    header, cleaned_turns = clean_turns(lines)

    # 1) Markdown
    md_text = render_markdown(header, cleaned_turns)
    md_path = output_base + ".md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print("Wrote Markdown:", md_path)

    # 2) HTML fragment
    html_fragment = render_html_fragment(header, cleaned_turns)
    html_path = output_base + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_fragment)
    print("Wrote HTML fragment:", html_path)

    # 3) Optional PDF
    pdf_path = output_base + ".pdf"
    write_pdf_from_markdown(md_path, pdf_path)


def main():
    if len(sys.argv) != 3:
        print("Usage: python clean_transcript.py input.txt output_basename")
        sys.exit(1)

    input_path = sys.argv[1]
    output_base = sys.argv[2].rsplit(".", 1)[0]  # strip extension if given

    clean_transcript(input_path, output_base)


if __name__ == "__main__":
    main()