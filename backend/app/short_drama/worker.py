"""独立于 ComfyUI Dispatcher 的创作任务 Worker。"""
from __future__ import annotations

import asyncio
import logging
try:  # Python 3.11+
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # Python 3.10 fallback
    from datetime import timezone as _tz
    UTC = _tz.utc  # type: ignore[assignment]
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import CreativeJob, Resource, SourceChapter, SourceDocument, SourceParagraph
from app.short_drama.parsers import ParserError, parse_document
from app.storage.local_fs import get_storage

logger = logging.getLogger(__name__)
SUPPORTED_JOB_TYPES = ("parse_document", "analyze_novel", "generate_adaptation", "generate_episode_screenplay", "generate_script_manifest", "director_story_ledger")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _append_log(job: CreativeJob, level: str, message: str) -> None:
    job.logs = [*list(job.logs or []), {"time": _now().isoformat(timespec="seconds") + "Z", "level": level, "message": message}]


class StoryWorker:
    def __init__(self) -> None:
        self._runner: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._runner and not self._runner.done():
            return
        self._stop = asyncio.Event()
        await asyncio.to_thread(self._recover_stale_jobs)
        self._runner = asyncio.create_task(self._run(), name="story-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._runner:
            await self._runner
        self._runner = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = await asyncio.to_thread(self._claim_next)
                if job_id is not None:
                    await asyncio.to_thread(self._process, job_id)
                    continue
            except Exception:  # noqa: BLE001
                logger.exception("Story Worker 循环异常")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.story_worker_poll_seconds)
            except TimeoutError:
                pass

    def _recover_stale_jobs(self) -> None:
        cutoff = _now() - timedelta(seconds=settings.story_worker_timeout_seconds)
        with SessionLocal() as db:
            jobs = db.query(CreativeJob).filter(
                CreativeJob.job_type.in_(SUPPORTED_JOB_TYPES),
                CreativeJob.status.in_(["running", "cancelling"]),
                CreativeJob.heartbeat_at < cutoff,
            ).all()
            for job in jobs:
                if job.retries >= settings.story_worker_max_retries:
                    job.status = "failed"
                    job.error = "Worker 超时且已达到自动恢复次数上限"
                    job.finished_at = _now()
                    _append_log(job, "error", job.error)
                else:
                    job.status = "queued"
                    job.retries += 1
                    job.progress = 0
                    _append_log(job, "warning", "检测到 Worker 中断，任务已自动重新排队")
            db.commit()

    def _claim_next(self) -> int | None:
        with SessionLocal() as db:
            job = db.query(CreativeJob).filter(
                CreativeJob.job_type.in_(SUPPORTED_JOB_TYPES), CreativeJob.status == "queued"
            ).order_by(CreativeJob.id).first()
            if not job:
                return None
            changed = db.query(CreativeJob).filter(
                CreativeJob.id == job.id, CreativeJob.status == "queued"
            ).update({
                CreativeJob.status: "running",
                CreativeJob.progress: 5,
                CreativeJob.started_at: _now(),
                CreativeJob.heartbeat_at: _now(),
            }, synchronize_session=False)
            if not changed:
                db.rollback()
                return None
            db.commit()
            return job.id

    @staticmethod
    def _set_progress(db: Session, job: CreativeJob, value: int, message: str) -> bool:
        db.refresh(job)
        if job.status == "cancelling":
            job.status = "cancelled"
            job.cancelled_at = _now()
            job.finished_at = job.cancelled_at
            _append_log(job, "warning", "任务已取消")
            db.commit()
            return False
        job.progress = value
        job.heartbeat_at = _now()
        _append_log(job, "info", message)
        db.commit()
        return True

    def _process(self, job_id: int) -> None:
        with SessionLocal() as db:
            job = db.get(CreativeJob, job_id)
            if not job or job.status != "running": return
            if job.job_type == "parse_document":
                return self._process_parse(job_id)
            try:
                from app.short_drama.ai_service import process_ai_job
                process_ai_job(db, job, self._set_progress)
            except Exception as exc:  # noqa: BLE001
                db.rollback(); job=db.get(CreativeJob,job_id)
                if job:self._fail(db,job,str(exc) or exc.__class__.__name__)

    def _process_parse(self, job_id: int) -> None:
        with SessionLocal() as db:
            job = db.get(CreativeJob, job_id)
            if not job or job.status != "running":
                return
            document = db.get(SourceDocument, int(job.input_payload.get("document_id", 0)))
            if not document or document.owner_id != job.owner_id:
                self._fail(db, job, "源文档记录不存在")
                return
            document.status = "parsing"
            document.error = None
            _append_log(job, "info", "开始读取素材库中的原始文档")
            db.commit()
            try:
                resource = db.get(Resource, document.resource_id)
                resource_key = resource.storage_key if resource and resource.owner_id == job.owner_id else None
                if not resource_key:
                    raise ParserError("素材文件不存在")
                content = get_storage().read(resource_key)
                if not self._set_progress(db, job, 25, "原始文档读取完成，正在解析结构"):
                    document.status = "cancelled"
                    db.commit()
                    return
                parsed = parse_document(content, document.filename)
                if not self._set_progress(db, job, 60, f"已识别 {len(parsed.chapters)} 个章节，正在保存"):
                    document.status = "cancelled"
                    db.commit()
                    return
                self._replace_content(db, job, document, parsed)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                job = db.get(CreativeJob, job_id)
                if job:
                    self._fail(db, job, str(exc) or exc.__class__.__name__)

    @staticmethod
    def _replace_content(db: Session, job: CreativeJob, document: SourceDocument, parsed) -> None:
        chapter_ids = [item.id for item in document.chapters]
        if chapter_ids:
            db.query(SourceParagraph).filter(SourceParagraph.chapter_id.in_(chapter_ids)).delete(synchronize_session=False)
            db.query(SourceChapter).filter(SourceChapter.id.in_(chapter_ids)).delete(synchronize_session=False)
            db.flush()
        for chapter_index, parsed_chapter in enumerate(parsed.chapters, start=1):
            chapter = SourceChapter(
                owner_id=job.owner_id,
                document_id=document.id,
                number=chapter_index,
                title=parsed_chapter.title,
                sort_order=chapter_index,
                paragraph_count=len(parsed_chapter.paragraphs),
                char_count=parsed_chapter.char_count,
            )
            db.add(chapter)
            db.flush()
            db.add_all([
                SourceParagraph(
                    owner_id=job.owner_id,
                    chapter_id=chapter.id,
                    paragraph_index=index,
                    text=text,
                    char_count=len(text),
                    source_locator=f"chapter:{chapter_index}/paragraph:{index}",
                )
                for index, text in enumerate(parsed_chapter.paragraphs, start=1)
            ])
        document.title = parsed.title[:255]
        document.encoding = parsed.encoding
        document.status = "ready"
        document.total_chapters = len(parsed.chapters)
        document.total_paragraphs = parsed.total_paragraphs
        document.total_chars = parsed.total_chars
        document.error = None
        job.status = "succeeded"
        job.progress = 100
        job.heartbeat_at = _now()
        job.finished_at = _now()
        job.output_payload = {
            "document_id": document.id,
            "title": document.title,
            "chapters": document.total_chapters,
            "paragraphs": document.total_paragraphs,
            "characters": document.total_chars,
        }
        _append_log(job, "info", "文档解析完成")
        db.commit()

    @staticmethod
    def _fail(db: Session, job: CreativeJob, message: str) -> None:
        job.status = "failed"
        job.error = message[:4000]
        job.finished_at = _now()
        job.heartbeat_at = _now()
        document = db.get(SourceDocument, int(job.input_payload.get("document_id", 0)))
        if document and job.job_type == "parse_document":
            document.status = "failed"
            document.error = job.error
        _append_log(job, "error", f"解析失败：{job.error}")
        db.commit()


story_worker = StoryWorker()
