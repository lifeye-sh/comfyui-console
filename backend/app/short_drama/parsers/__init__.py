"""短剧源文档解析器。"""

from app.short_drama.parsers.dispatcher import parse_document
from app.short_drama.parsers.types import ParsedChapter, ParsedDocument, ParserError

__all__ = ["ParsedChapter", "ParsedDocument", "ParserError", "parse_document"]
