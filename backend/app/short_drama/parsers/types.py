"""不同文档格式共享的解析结果。"""
from __future__ import annotations

from dataclasses import dataclass, field


class ParserError(ValueError):
    """文档无法安全、完整地解析。"""


@dataclass
class ParsedChapter:
    number: int
    title: str | None
    paragraphs: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(item) for item in self.paragraphs)


@dataclass
class ParsedDocument:
    title: str
    source_format: str
    chapters: list[ParsedChapter] = field(default_factory=list)
    encoding: str | None = None

    @property
    def total_chars(self) -> int:
        return sum(item.char_count for item in self.chapters)

    @property
    def total_paragraphs(self) -> int:
        return sum(len(item.paragraphs) for item in self.chapters)
