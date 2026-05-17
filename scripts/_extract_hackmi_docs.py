"""Extract plain-text from every HackMI .docx and .pptx in C:\\Users\\sudar\\Downloads.

Uses only stdlib (zipfile + xml.etree) so it runs without extra deps.
Writes each extracted text to C:\\Users\\sudar\\frankie\\data\\hackmi_docs\\.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

DOWNLOADS = Path(r"C:\Users\sudar\Downloads")
OUT = Path(r"C:\Users\sudar\frankie\data\hackmi_docs")

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def extract_docx(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        for para in root.iter(W_NS + "p"):
            text = "".join(t.text or "" for t in para.iter(W_NS + "t"))
            if text.strip():
                chunks.append(text)
    return "\n".join(chunks)


def extract_pptx(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as z:
        slide_files = sorted(
            n for n in z.namelist()
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        for i, name in enumerate(slide_files, 1):
            chunks.append(f"\n--- Slide {i} ({name}) ---")
            with z.open(name) as f:
                tree = ET.parse(f)
            root = tree.getroot()
            for t in root.iter(A_NS + "t"):
                if t.text and t.text.strip():
                    chunks.append(t.text.strip())
    return "\n".join(chunks)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(
        list(DOWNLOADS.glob("*.docx")) + list(DOWNLOADS.glob("*.pptx"))
    )
    hack_files = [f for f in files if re.search(r"(?i)hack|ibm-bob", f.name)]
    if not hack_files:
        print("No HackMI/IBM files found in Downloads.", file=sys.stderr)
        return 1
    for f in hack_files:
        out_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", f.stem) + ".txt"
        out_path = OUT / out_name
        try:
            text = extract_docx(f) if f.suffix.lower() == ".docx" else extract_pptx(f)
        except Exception as exc:
            print(f"FAIL {f.name}: {exc}", file=sys.stderr)
            continue
        out_path.write_text(text, encoding="utf-8")
        print(f"{f.name} -> {out_path.relative_to(OUT.parent.parent)} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
