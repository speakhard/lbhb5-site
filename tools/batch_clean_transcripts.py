#!/usr/bin/env python3
"""
Batch cleaner for Babylon 5 podcast transcripts.

- Reads .txt files from raw_transcripts/
- Uses clean_transcript.clean_transcript() to generate:
    transcripts/<slug>.md
    transcripts/<slug>.html
    transcripts/<slug>.pdf (optional, via pandoc)
- Moves processed .txt files into processed_transcripts/
"""

from pathlib import Path
import shutil
import re
import sys

# Figure out project root and make sure tools/ is on sys.path
THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parent

sys.path.insert(0, str(THIS_DIR))  # so we can import clean_transcript from tools/

from clean_transcript import clean_transcript  # now imports tools/clean_transcript.py

RAW_DIR = ROOT / "raw_transcripts"
OUT_DIR = ROOT / "transcripts"
PROCESSED_DIR = ROOT / "processed_transcripts"

def slugify_filename(name: str) -> str:
    """
    Turn a raw filename like:
        "1-chrysalis.txt"
        "Who Are You (COMES THE INQUISITOR).txt"
    into a slug like:
        "1-chrysalis"
        "who-are-you-comes-the-inquisitor"
    """
    base = name.rsplit(".", 1)[0]
    base = base.lower().strip()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    return base or "episode"


def process_one(raw_path: Path) -> None:
    slug = slugify_filename(raw_path.name)
    base = OUT_DIR / slug  # <== NO extension here

    print(f"Processing: {raw_path.name} -> {base}")

    # This will create:
    #   <base>.md
    #   <base>.html
    #   <base>.pdf (optional, via pandoc)
    clean_transcript(str(raw_path), str(base))

    # Move the original raw file into processed_transcripts/
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / raw_path.name
    shutil.move(str(raw_path), dest)
    print(f"Moved raw file to {dest}")
    print("-" * 60)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(RAW_DIR.glob("*.txt"))
    if not txt_files:
        print("No .txt files found in raw_transcripts/. Nothing to do.")
        return

    for raw_path in txt_files:
        process_one(raw_path)


if __name__ == "__main__":
    main()
