#!/usr/bin/env python3
"""
Babylon 5 podcast transcript cleaner.

Usage:
    python3 tools/clean_transcript.py input.txt output_basename

Creates:
    output_basename.md
    output_basename.html
    output_basename.pdf (optional, if pandoc is installed)

Expected (preferred) input line format:
    [00:00:00] JOSH: blah blah

But this parser is more forgiving:
    - speaker can be mixed case
    - speaker can include spaces, hyphens, dots
    - ignores extra whitespace
"""

from __future__ import annotations

import re
import sys
import subprocess
import shutil
from typing import List, Dict, Tuple, Optional
import html as html_lib

# More permissive:
#   [HH:MM:SS] <speaker>: <text>
# speaker: anything up to ":" (but not absurdly long)
TC_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\]\s*([^:]{1,60})\s*:\s*(.*)\s*$"
)

def escape(s: str) -> str:
    return html_lib.escape(s, quote=True)

def normalize_speaker(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # Optional: force uppercase labels
    # Comment this out if you want original casing
    return s.upper()

def clean_dialog(d: str) -> str:
    # Normalize whitespace first
    d = re.sub(r"\s+", " ", d).strip()

    # Custom replacements
    d = d.replace("mapable", "mappable")
    d = d.replace("antia sentiment", "anti-alien sentiment")
    d = re.sub(r"\bThat's been\b", "It's been", d)

    # Filler cleanup (light touch)
    d = re.sub(r'^\s*(Um|Uh)[\.,]?\s+', '', d, flags=re.I)
    d = re.sub(r'\b(um|uh)[\.,]?\b', '', d, flags=re.I)
    d = re.sub(r'\byou know,?\s*', '', d, flags=re.I)
    d = re.sub(r'\blike,\s+(?=(you|we|I|it|that)\b)', '', d, flags=re.I)

    # Collapse stray line breaks caused by ASR
    d = re.sub(r'\s*\n\s*', ' ', d)

    # Fix space before punctuation
    d = re.sub(r'\s+([,.!?])', r'\1', d)

    d = re.sub(r"\s{2,}", " ", d).strip()

    # Punctuation smoothing (keep conservative; don’t wreck timecodes)
    d = d.replace("—", ",")
    # Don’t replace ":" globally; it can be meaningful in quotes/titles

    return d

def group_turns(lines: List[str]) -> Tuple[Optional[Dict], List[Dict]]:
    """
    Groups raw lines into turns. Any line that matches TC_RE begins a new turn.
    Any non-matching non-empty line after a turn is treated as continuation
    of that turn (hard-wrap fix).
    """
    turns: List[Dict] = []
    current: Optional[Dict] = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        m = TC_RE.match(line.strip())
        if m:
            if current:
                turns.append(current)
            tc, spk, txt = m.groups()
            current = {
                "time": tc,
                "speaker": normalize_speaker(spk),
                "text": txt.strip(),
            }
            continue

        # blank line: ignore (don’t create fake paragraphs)
        if not line.strip():
            continue

        # continuation line
        if current:
            s = line.strip()
            if s:
                # merge hard-wrapped line into current text
                current["text"] = (current["text"].rstrip() + " " + s).strip()
        else:
            # preface text before first timecode
            turns.append({"time": None, "speaker": None, "text": line.strip()})

    if current:
        turns.append(current)

    # Header/preface: if the first entry has no timecode, treat it as header
    header = None
    if turns and turns[0]["time"] is None:
        header = turns[0]
        turns = turns[1:]

    return header, turns

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

def render_markdown(header: Optional[Dict], turns: List[Dict]) -> str:
    out: List[str] = []
    if header and header.get("text"):
        out.append(header["text"].strip())
        out.append("")

    for t in turns:
        if not t["time"]:
            out.append(t["text"])
        else:
            out.append(f"[{t['time']}] **{t['speaker']}**, {t['text']}")

    return "\n\n".join(out).strip() + "\n"

def render_html_fragment(header: Optional[Dict], turns: List[Dict]) -> str:
    """
    HTML fragment with <span class="tc"> for timestamp toggling.
    """
    lines: List[str] = []
    lines.append('<div class="transcript-body">')

    if header and header.get("text"):
        lines.append(f'  <p class="transcript-preface">{escape(header["text"])}</p>')

    for t in turns:
        if not t["time"]:
            lines.append(f'  <p class="transcript-note">{escape(t["text"])}</p>')
        else:
            tc = escape(t["time"])
            speaker = escape(t["speaker"])
            text = escape(t["text"])
            lines.append(
                '  <p class="transcript-turn">'
                f'<span class="tc" data-tc="{tc}">[{tc}]</span> '
                f'<span class="speaker">{speaker}</span>, '
                f'<span class="line">{text}</span>'
                "</p>"
            )

    lines.append("</div>")
    return "\n".join(lines) + "\n"

def write_pdf_from_markdown(md_path: str, pdf_path: str) -> None:
    if shutil.which("pandoc") is None:
        print("pandoc not found; skipping PDF for", md_path)
        return

    try:
        subprocess.run(["pandoc", md_path, "-o", pdf_path], check=True)
        print("Wrote PDF:", pdf_path)
    except subprocess.CalledProcessError as e:
        print("pandoc failed, skipping PDF:", e)

def clean_transcript(input_path: str, output_base: str) -> None:
    raw = open(input_path, encoding="utf-8", errors="replace").read()
    lines = raw.splitlines()

    header, cleaned_turns = clean_turns(lines)

    # If we detected *zero* timecoded turns, warn loudly.
    has_any_tc = any(t.get("time") for t in cleaned_turns)
    if not has_any_tc:
        print("WARNING: No timecoded lines matched. Check your input format.")

    md_path = output_base + ".md"
    html_path = output_base + ".html"
    pdf_path = output_base + ".pdf"

    md_text = render_markdown(header, cleaned_turns)
    open(md_path, "w", encoding="utf-8").write(md_text)
    print("Wrote Markdown:", md_path)

    html_fragment = render_html_fragment(header, cleaned_turns)
    open(html_path, "w", encoding="utf-8").write(html_fragment)
    print("Wrote HTML fragment:", html_path)

    write_pdf_from_markdown(md_path, pdf_path)

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 tools/clean_transcript.py input.txt output_basename")
        sys.exit(1)

    input_path = sys.argv[1]
    output_base = sys.argv[2].rsplit(".", 1)[0]
    clean_transcript(input_path, output_base)

if __name__ == "__main__":
    main()
