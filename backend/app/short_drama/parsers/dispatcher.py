"""TXT、DOCX、EPUB 的无第三方依赖解析入口。"""
from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from app.short_drama.parsers.text import decode_text, parse_text
from app.short_drama.parsers.types import ParsedChapter, ParsedDocument, ParserError

MAX_ARCHIVE_ENTRIES = 5000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _safe_zip(content: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ParserError("文件不是有效的 ZIP 文档") from exc
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES or sum(item.file_size for item in entries) > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise ParserError("文档解压后体积过大")
    return archive


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _docx(content: bytes, title: str) -> ParsedDocument:
    with _safe_zip(content) as archive:
        try:
            root = ET.fromstring(archive.read("word/document.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise ParserError("DOCX 正文结构损坏") from exc
        paragraphs: list[tuple[str, bool]] = []
        for element in root.iter():
            if _local_name(element.tag) != "p":
                continue
            text = "".join(node.text or "" for node in element.iter() if _local_name(node.tag) in {"t", "tab", "br"}).strip()
            if not text:
                continue
            style = next((node for node in element.iter() if _local_name(node.tag) == "pStyle"), None)
            style_value = ""
            if style is not None:
                style_value = next(iter(style.attrib.values()), "")
            paragraphs.append((text, bool(re.match(r"^(Heading|标题)[ _]?[12]$", style_value, re.IGNORECASE))))
        try:
            props = ET.fromstring(archive.read("docProps/core.xml"))
            meta_title = next((node.text for node in props.iter() if _local_name(node.tag) == "title" and node.text), None)
            title = meta_title or title
        except (KeyError, ET.ParseError):
            pass
    if not paragraphs:
        raise ParserError("DOCX 中没有正文")
    if not any(is_heading for _, is_heading in paragraphs):
        return parse_text("\n\n".join(text for text, _ in paragraphs), title, "docx")
    chapters: list[ParsedChapter] = []
    current_title: str | None = None
    current: list[str] = []
    for text, is_heading in paragraphs:
        if is_heading:
            if current:
                chapters.append(ParsedChapter(len(chapters) + 1, current_title, current))
            current_title, current = text, []
        else:
            current.append(text)
    if current:
        chapters.append(ParsedChapter(len(chapters) + 1, current_title, current))
    if not chapters:
        raise ParserError("DOCX 标题后没有正文")
    return ParsedDocument(title=title, source_format="docx", chapters=chapters)


class _XhtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.title: str | None = None
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"p", "h1", "h2", "h3"}:
            self.capture, self.buffer = tag.lower(), []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture != tag.lower():
            return
        value = " ".join("".join(self.buffer).split())
        if value:
            if self.capture == "p":
                self.paragraphs.append(value)
            elif self.title is None:
                self.title = value
        self.capture, self.buffer = None, []


def _epub(content: bytes, title: str) -> ParsedDocument:
    with _safe_zip(content) as archive:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(node for node in container.iter() if _local_name(node.tag) == "rootfile")
            opf_path = rootfile.attrib["full-path"]
            opf = ET.fromstring(archive.read(opf_path))
        except (KeyError, StopIteration, ET.ParseError) as exc:
            raise ParserError("EPUB 目录结构损坏") from exc
        for node in opf.iter():
            if _local_name(node.tag) == "title" and node.text and node.text.strip():
                title = node.text.strip()
                break
        manifest = {
            node.attrib.get("id", ""): node.attrib.get("href", "")
            for node in opf.iter() if _local_name(node.tag) == "item"
        }
        spine = [node.attrib.get("idref", "") for node in opf.iter() if _local_name(node.tag) == "itemref"]
        base = posixpath.dirname(opf_path)
        chapters: list[ParsedChapter] = []
        for item_id in spine:
            href = manifest.get(item_id)
            if not href:
                continue
            path = posixpath.normpath(posixpath.join(base, href.split("#", 1)[0]))
            if path.startswith("../"):
                continue
            try:
                html = archive.read(path).decode("utf-8", errors="replace")
            except KeyError:
                continue
            parser = _XhtmlExtractor()
            parser.feed(html)
            if parser.paragraphs:
                chapters.append(ParsedChapter(len(chapters) + 1, parser.title, parser.paragraphs))
    if not chapters:
        raise ParserError("EPUB 中没有提取到有效正文")
    return ParsedDocument(title=title, source_format="epub", chapters=chapters)


def parse_document(content: bytes, filename: str) -> ParsedDocument:
    if not content:
        raise ParserError("文件内容为空")
    path = Path(filename)
    suffix = path.suffix.lower()
    title = path.stem or "未命名作品"
    if suffix == ".txt":
        text, encoding = decode_text(content)
        return parse_text(text, title, encoding=encoding)
    if suffix == ".docx":
        return _docx(content, title)
    if suffix == ".epub":
        return _epub(content, title)
    raise ParserError("仅支持 TXT、DOCX、EPUB 文件")
