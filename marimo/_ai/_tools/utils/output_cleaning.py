# Copyright 2026 Marimo. All rights reserved.

from __future__ import annotations

import re
from typing import Optional

# MIME types whose content should be masked when exceeding the size threshold.
# text/plain and text/markdown are intentionally excluded — they are already
# compact and useful for agents.
MASKING_MIMETYPES = frozenset(
    {
        "application/json",
        "text/html",
        "text/csv",
        "image/png",
        "image/svg+xml",
        "image/jpeg",
        "image/gif",
        "image/tiff",
        "image/avif",
        "image/bmp",
        "application/vnd.vega.v5+json",
        "application/vnd.vegalite.v5+json",
        "application/vnd.vega.v6+json",
        "application/vnd.vegalite.v6+json",
        "application/vnd.jupyter.widget-view+json",
        "video/mp4",
        "video/mpeg",
    }
)

# JSON-like MIME types that get simple character truncation.
_JSON_MIMETYPES = frozenset(
    {
        "application/json",
        "application/vnd.vega.v5+json",
        "application/vnd.vegalite.v5+json",
        "application/vnd.vega.v6+json",
        "application/vnd.vegalite.v6+json",
    }
)

_ACCORDION_LABELS_RE = re.compile(r'"labels"\s*:\s*\[([^\]]*)\]', re.DOTALL)

# Cap for the markdown conversion result — keeps output useful but bounded.
_MAX_MARKDOWN_CHARS = 5000


def mask_visual_output(
    data: str,
    mimetype: str,
    threshold: int = 5120,
) -> tuple[str, bool]:
    """Replace large visual outputs with a compact representation.

    For ``text/html``, converts to markdown so agents retain useful
    textual content. Other large binary/visual types get a placeholder.

    Returns ``(data, was_masked)`` — the caller can use the flag to
    annotate the output for agents.
    """
    if mimetype not in MASKING_MIMETYPES:
        return data, False

    byte_size = len(data.encode("utf-8"))
    if byte_size <= threshold:
        return data, False

    # HTML → markdown conversion preserves actionable content
    if mimetype == "text/html":
        return _html_to_markdown(data), True

    # JSON-like types get simple character truncation
    if mimetype in _JSON_MIMETYPES:
        return _truncate_text(data, threshold), True

    # CSV gets line-based truncation
    if mimetype == "text/csv":
        return _truncate_csv(data), True

    placeholder = (
        f"[Visual output masked: {mimetype}, {byte_size} bytes. "
        f"Use the notebook UI to view this output.]"
    )
    return placeholder, True


def _html_to_markdown(html: str) -> str:
    """Convert HTML to a compact markdown representation.

    Handles tables, headings, links, lists, and falls back to text
    extraction. Accordion labels are surfaced as section headers.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    parts: list[str] = []

    # Extract accordion labels if present
    accordion_hint = _extract_accordion_labels(html)
    if accordion_hint:
        parts.append(f"Sections: {accordion_hint}")

    # Remove script/style tags — never useful
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Convert tables to markdown tables
    for table in soup.find_all("table"):
        md_table = _table_to_markdown(table)
        if md_table:
            table.replace_with(md_table)

    # Convert headings
    for level in range(1, 7):
        for heading in soup.find_all(f"h{level}"):
            text = heading.get_text(strip=True)
            if text:
                heading.replace_with(f"\n{'#' * level} {text}\n")

    # Convert links
    for a in soup.find_all("a"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if href and text:
            a.replace_with(f"[{text}]({href})")
        elif text:
            a.replace_with(text)

    # Convert list items
    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        if text:
            li.replace_with(f"\n- {text}")

    # Get remaining text
    text = soup.get_text(separator="\n")

    # Clean up whitespace: collapse blank lines
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(lines)
    # Collapse 3+ newlines into 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    if parts:
        cleaned = "\n".join(parts) + "\n\n" + cleaned

    # Truncate if still too long
    if len(cleaned) > _MAX_MARKDOWN_CHARS:
        half = _MAX_MARKDOWN_CHARS // 2
        cleaned = (
            cleaned[:half]
            + f"\n\n... [truncated {len(cleaned) - _MAX_MARKDOWN_CHARS} chars] ...\n\n"
            + cleaned[-half:]
        )

    return f"[Parsed from HTML output]\n{cleaned}"


def _table_to_markdown(table: object) -> str:
    """Convert an HTML <table> to a markdown table string."""
    from bs4 import Tag

    if not isinstance(table, Tag):
        return ""

    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        if not isinstance(tr, Tag):
            continue
        cells = []
        for cell in tr.find_all(["th", "td"]):
            cells.append(cell.get_text(strip=True))
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    # Build markdown table
    lines: list[str] = []
    header = rows[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n" + "\n".join(lines) + "\n"


def _extract_accordion_labels(data: str) -> Optional[str]:
    """Try to extract accordion section labels from HTML output."""
    if "<marimo-accordion" not in data:
        return None
    match = _ACCORDION_LABELS_RE.search(data)
    if not match:
        return None
    raw = match.group(1).strip()
    if not raw:
        return None
    # Parse JSON-style string list: "label1", "label2"
    labels = [
        s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()
    ]
    return ", ".join(labels) if labels else None


def _truncate_text(data: str, max_chars: int) -> str:
    """Truncate text to *max_chars*, appending a remainder note."""
    if len(data) <= max_chars:
        return data
    remaining = len(data) - max_chars
    return data[:max_chars] + f"\n... [{remaining} more chars]"


_CSV_MAX_LINES = 100


def _truncate_csv(data: str) -> str:
    """Keep the header and first 100 data lines of CSV output."""
    lines = data.splitlines(keepends=True)
    if len(lines) <= _CSV_MAX_LINES + 1:  # +1 for header
        return data
    kept = lines[: _CSV_MAX_LINES + 1]
    omitted = len(lines) - _CSV_MAX_LINES - 1
    return "".join(kept) + f"... [{omitted} more rows]"


def clean_output(lines: list[str]) -> list[str]:
    """Clean console output for LLM consumption."""
    lines = normalize_progress_bars(lines)
    lines = deduplicate_lines(lines)
    lines = strip_ansi_codes(lines)
    lines = truncate_output(lines)
    return lines


def strip_ansi_codes(lines: list[str]) -> list[str]:
    """Remove ANSI escape sequences (colors, formatting) from text.

    ANSI codes are used for terminal styling (colors, bold, cursor movement,
    etc.) from libraries like rich, pytest, click, tqdm, colorama. These are
    meaningless to LLMs and add noise to the output.
    """
    # Based on a widely cited Stack Overflow answer:
    # https://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
    # Covers all 7-bit ANSI C1 escape sequences.
    ansi_pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return [ansi_pattern.sub("", line) for line in lines]


def deduplicate_lines(lines: list[str]) -> list[str]:
    """Remove consecutive duplicate lines, replacing with a summary message.

    Useful for cleaning repetitive training logs, warnings, and batch processing output.
    """
    if len(lines) <= 1:
        return lines

    deduped_lines: list[str] = []
    prev_line = lines[0]
    repeat_count = 1

    for line in lines[1:]:
        if line == prev_line:
            repeat_count += 1
            continue
        # Flush previous group
        deduped_lines.append(prev_line)
        if repeat_count > 1:
            deduped_lines.append(f"(repeated {repeat_count} times)")

        # Start new group
        prev_line = line
        repeat_count = 1

    # Handle last group
    deduped_lines.append(prev_line)
    if repeat_count > 1:
        deduped_lines.append(f"(repeated {repeat_count} times)")

    return deduped_lines


def normalize_progress_bars(lines: list[str]) -> list[str]:
    """Collapse carriage return sequences to show only final state.

    Progress bars from tqdm, pandas.progress_apply(), dask, and Spark use
    carriage returns to overwrite the same line repeatedly. This keeps only
    the final state and removes empty lines.
    """
    normalized_lines: list[str] = []
    for line in lines:
        if "\r" in line:
            line = line.split("\r")[-1]
        if line.strip():
            normalized_lines.append(line)
    return normalized_lines


def truncate_output(lines: list[str], max_lines: int = 500) -> list[str]:
    """Keep first and last portions of output, truncating the middle."""
    if len(lines) <= max_lines:
        return lines

    keep_head = max_lines // 2
    keep_tail = max_lines - keep_head
    removed = len(lines) - max_lines

    return (
        lines[:keep_head]
        + [f"... [truncated {removed} lines] ..."]
        + lines[-keep_tail:]
    )
