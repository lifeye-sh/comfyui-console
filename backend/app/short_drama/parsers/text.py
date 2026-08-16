"""TXT 内容分章。"""
from __future__ import annotations

import re

from app.short_drama.parsers.types import ParsedChapter, ParsedDocument, ParserError

_CHAPTER_PATTERNS = (
    re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章回节卷篇](?:\s+(.+))?\s*$"),
    re.compile(r"^\s*Chapter\s+\d+(?:\s*[:\-—]\s*(.+))?\s*$", re.IGNORECASE),
    re.compile(r"^\s*#{1,2}\s+(.+)\s*$"),
    re.compile(r"^\s*\d+[.、]\s+(.+)\s*$"),
)


def decode_text(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ParserError("文本编码无法识别，请转换为 UTF-8 或 GB18030 后重试")


def _heading(line: str) -> str | None | bool:
    for pattern in _CHAPTER_PATTERNS:
        match = pattern.match(line)
        if match:
            return match.group(1).strip() if match.lastindex and match.group(1) else None
    return False


def _paragraphs(lines: list[str]) -> list[str]:
    result: list[str] = []
    buffer: list[str] = []
    for line in lines:
        value = line.strip()
        if value:
            buffer.append(value)
        elif buffer:
            result.append("".join(buffer))
            buffer = []
    if buffer:
        result.append("".join(buffer))
    return result


def parse_text(text: str, default_title: str, source_format: str = "txt", encoding: str | None = None) -> ParsedDocument:
    if not text.strip():
        raise ParserError("文件内容为空")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title = default_title
    for line in lines[:5]:
        value = line.strip()
        if value:
            if len(value) <= 80 and _heading(value) is False:
                title = value
            break

    boundaries: list[tuple[int, str | None]] = []
    for index, line in enumerate(lines):
        heading = _heading(line)
        if heading is not False:
            boundaries.append((index, heading))

    chapters: list[ParsedChapter] = []
    if not boundaries:
        content = _paragraphs(lines)
        if content:
            chapters.append(ParsedChapter(number=1, title=None, paragraphs=content))
    else:
        for index, (line_index, chapter_title) in enumerate(boundaries):
            end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(lines)
            content = _paragraphs(lines[line_index + 1:end])
            if content:
                chapters.append(ParsedChapter(len(chapters) + 1, chapter_title, content))
    if not chapters:
        raise ParserError("没有提取到有效正文")
    return ParsedDocument(title=title, source_format=source_format, chapters=chapters, encoding=encoding)
