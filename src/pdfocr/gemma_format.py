"""Opt-in presentation cleanup; retain one exact contiguous source interval."""

import re


def unwrap_presentation(text: str) -> dict:
    start, end = 0, len(text)
    operations = []
    fence = re.fullmatch(r"\s*```(?:markdown|md)?[ \t]*\n(.*?)\n```[ \t]*\s*", text, re.S)
    if fence and "```" not in fence[1]:
        start, end = fence.start(1), fence.end(1)
        operations.append("single_outer_markdown_fence")
    metadata_seen = False
    while start < end:
        remaining = text[start:end]
        heading = re.match(
            r"\s*#{1,6}[ \t]+(?:Page[ \t]+\d+|Transcription of Page[ \t]+\d+)[ \t]*\n", remaining
        )
        furniture = re.match(r"\s*[-—–]+[ \t]*\d{1,4}[ \t]*[-—–]+[ \t]*\n", remaining)
        divider = re.match(r"\s*-{3,}[ \t]*\n", remaining) if metadata_seen else None
        match = heading or furniture or divider
        if not match:
            break
        operations.append("leading_page_metadata" if heading or furniture else "metadata_divider")
        start += match.end()
        metadata_seen = True
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return {
        "markdown": text[start:end],
        "source_start": start,
        "source_end": end,
        "operations": operations,
    }
