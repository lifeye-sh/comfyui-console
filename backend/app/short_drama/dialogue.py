"""Dialogue spans retain exact source offsets; uncertain attribution stays visible."""
from __future__ import annotations
import re
from typing import Any, Iterable

PRONOUNCEABLE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
LABELS = {"场景", "地点", "时间", "画面", "动作任务", "镜头备注", "对白", "台词", "旁白", "内心独白", "出场人物", "环境氛围", "动作", "表情", "核心前提", "镜号", "节奏", "情绪", "音效", "字幕", "OS", "VO"}
NAME = r"[\u3400-\u9fffA-Za-z0-9_·]{1,16}"
LABEL = re.compile(rf"^\s*(?:[-*]\s+)?(?:\*\*)?(?:对白[：:]\s*|台词[：:]\s*)?@?(?P<name>{NAME})(?:\s*(?P<note>[（(][^）)]*[）)]|(?:V\.?O\.?|O\.?S\.?)))?(?:\*\*)?\s*[：:]\s*(?:\*\*)?", re.I)
BLOCK = re.compile(rf"^\s*(?:\*\*)?@(?P<name>{NAME})(?P<note>[（(][^）)]*[）)])?(?:\*\*)?\s*$")
QUOTE_PAIRS = {'“':'”', '「':'」', '『':'』', '‘':'’', '"':'"'}
SPEECH = re.compile(r"说|问|答|喊|叫|回应|重复|安抚|吼|低语|嘀咕|嘟囔|嚷|叮嘱|提醒|打断|开口|指挥|解释|道[：:]?\s*$|低笑[：:]?\s*$")
THOUGHT = re.compile(r"心想|心道|暗想|暗道|默念|心(?:里|中).{0,8}(?:想|说|自语|嘀咕|默念)|内心独白|OS[：:]?\s*$", re.I)
NON_SPEECH = re.compile(r"写着|写下|标着|字样|名为|所谓|称为|叫做|字幕|音效|拟声")


def _quotes(text: str) -> list[tuple[int, int]]:
    result = []
    index = 0
    while index < len(text):
        closing = QUOTE_PAIRS.get(text[index])
        if not closing:
            index += 1; continue
        end = text.find(closing, index + 1)
        if end < 0:
            index += 1; continue
        result.append((index + 1, end))
        index = end + 1
    return result


def _name_map(names: Iterable[str] | dict[str, str] | None) -> dict[str, str]:
    result = dict(names) if isinstance(names, dict) else {str(n):str(n) for n in (names or []) if n}
    # Unique short names commonly used in prose (苏沐橙 -> 沐橙).
    for name in list(result):
        if 3 <= len(name) <= 4 and len([n for n in result if n.endswith(name[-2:])]) == 1:
            result.setdefault(name[-2:], result[name])
    return result


def _subject(context: str, names: dict[str, str], *, after: bool = False) -> str:
    if not context or THOUGHT.search(context):
        return ""
    # A direct attribution is safe even without an asset dictionary.
    direct = re.match(rf"\s*(?P<name>{NAME}?)(?:轻声|低声|大声|柔声|急忙|笑着|哭着|继续)?(?:说道|问道|答道|回答|回应|重复|喊道|叫停|说|问|答|喊|道)[，。,:：\s]*$", context)
    if direct and direct['name'] not in LABELS and (direct['name'] in names or (not names and len(direct['name']) <= 4)):
        return names.get(direct['name'], direct['name'])
    matches = list(re.finditer('|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True)), context)) if names else []
    candidates = []
    for match in matches:
        before = context[:match.start()]
        clause = re.split(r'[，,。！？!?；;\n]', before)[-1]
        # A name governed by 对/向/看着 is an object, not the speaker.
        if re.search(r'(?:对|向|朝|给|看着|望着|听见|听到|看向|让|把|被|到)[^，,。！？!?；;\n]*$', clause):
            continue
        suffix = context[match.end():]
        if after and re.match(r"(?:听|看|望)", suffix):
            continue
        if after and not ('说完' in before[-8:] or SPEECH.search(suffix) or re.match(r'.{0,8}(?:的声音|的嗓音)', suffix)):
            continue
        candidates.append(names[match.group()])
    # Multiple subjects in an unresolved clause must not be guessed.
    if len(set(candidates)) == 1:
        return candidates[0]
    if candidates:
        clause = re.split(r'[，,。！？!?；;\n]', context)[-1]
        beginning = next((canonical for alias, canonical in names.items() if clause.strip().startswith(alias)), '')
        return beginning
    return ""


def dialogue_spans(content: str, character_names: Iterable[str] | dict[str, str] | None = None) -> list[dict[str, Any]]:
    text = content or ""
    names = _name_map(character_names)
    has_cast = bool(names)
    def safe_label(label, line: str):
        if not label: return None
        name = label['name']
        if name in LABELS or name in names: return label
        # With a cast dictionary, arbitrary short fields before a colon are much
        # more likely to be screenplay metadata (镜头10、服装6、时间预算...) than
        # speakers. Explicit @speaker blocks remain supported.
        if has_cast and not re.match(r"^\s*(?:[-*]\s+)?(?:\*\*)?@", line):
            return None
        if SPEECH.search(name): return None
        if re.fullmatch(r'[A-Za-z0-9_·]+',name) or len(name) <= 6: return label
        return None
    lines = []
    offset = 0
    pending = None
    result: list[dict[str, Any]] = []
    def add(start, end, speaker, block_start, offscreen=False, attribution='explicit'):
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end-1].isspace(): end -= 1
        if start >= end: return
        result.append({'speaker':speaker, 'text':text[start:end], 'start':start, 'end':end,
                       'block_start':block_start, 'line_index':text.count('\n',0,block_start),
                       'offscreen':offscreen, 'attribution':attribution, 'needs_review':not bool(speaker)})
    for raw in text.splitlines(keepends=True):
        line = raw.rstrip('\r\n'); label = safe_label(LABEL.match(line), line); block = BLOCK.match(line)
        lines.append((offset,offset+len(raw),line,label,pending))
        if block:
            pending = (names.get(block['name'],block['name']), offset, '画外' in (block['note'] or '') or 'VO' in (block['note'] or '').upper())
        elif line.strip() and not re.fullmatch(r'\s*[（(][^）)]*[）)]\s*',line):
            if label and label['name'] not in LABELS:
                names.setdefault(label['name'],label['name'])
                body = line[label.end():]
                # Quoted bodies are handled below, avoiding actions outside quotes.
                if body.strip() and not _quotes(body):
                    add(offset+label.end(),offset+len(line),names.get(label['name'],label['name']),offset,
                        bool(re.search(r'画外|V\.?O\.?',label['note'] or '',re.I)))
            elif pending and not _quotes(line) and not label and not line.lstrip().startswith(('#','[')):
                add(offset,offset+len(line),pending[0],pending[1],pending[2])
            pending = None
        offset += len(raw)
    quotes = _quotes(text)
    for index,(start,end) in enumerate(quotes):
        line_start,line_end,line,label,block = next((row for row in lines if row[0] <= start-1 < row[1]), (0,len(text),text,None,None))
        if any(x['start'] <= start and end <= x['end'] for x in result): continue
        if label and label['name'] in {'旁白','内心独白','音效','字幕','OS'}: continue
        previous_end = quotes[index-1][1]+1 if index else 0
        next_start = quotes[index+1][0]-1 if index+1 < len(quotes) else len(text)
        before = text[max(previous_end,line_start):start-1]
        after = text[end+1:min(next_start, text.find('\n',end+1) if '\n' in text[end+1:] else len(text))]
        if THOUGHT.search(before) or NON_SPEECH.search(before[-25:]): continue
        speaker='';offscreen=False;block_start=start-1;attribution='context'
        if label and start-1 >= line_start+label.end() and not text[line_start+label.end():start-1].strip():
            speaker=names.get(label['name'],label['name'])
            offscreen=bool(re.search(r'画外|V\.?O\.?',label['note'] or '',re.I));block_start=line_start;attribution='explicit'
        elif block and not before.strip():
            speaker,block_start,offscreen=block;attribution='explicit'
        else:
            # Use only the current sentence; a prior speaker must not leak into a new turn.
            context = re.split(r'[。！？!?；;\n]',before)[-1]
            if SPEECH.search(context) or context.rstrip().endswith(('：',':')):
                speaker=_subject(context.rstrip('：: '),names)
                if not speaker and len(re.findall(r'[。！？!?；;]',before)):
                    speaker=_subject(before.rstrip('：: '),names)
            if not speaker:
                speaker=_subject(after,names,after=True)
            if not speaker and not before.strip():
                # A preceding line ending with an explicit speech cue may own this quote.
                preceding=text[:line_start].rstrip().split('\n')[-1] if text[:line_start].strip() else ''
                if preceding.endswith(('：',':')) and SPEECH.search(preceding):
                    speaker=_subject(preceding.rstrip('：: '),names)
        # Repeated short sound effects are not spoken dialogue.
        value=text[start:end]
        if re.fullmatch(r'[嘭砰咚轰哗滴叮啪嗒哒]+',value) and not speaker: continue
        add(start,end,speaker,block_start,offscreen,attribution if speaker else 'unresolved')
    return sorted(result,key=lambda x:x['start'])


def extract_dialogue_lines(content: str, character_names: Iterable[str] | dict[str, str] | None = None) -> list[dict[str, str]]:
    return [{'speaker':item['speaker'],'text':item['text']} for item in dialogue_spans(content,character_names)]


def dialogue_metrics(text: str, shot_duration: float, reaction_pause: float = 0) -> dict[str, Any]:
    spoken = len(PRONOUNCEABLE.findall(text or ""))
    counts = [len(PRONOUNCEABLE.findall(part)) for part in re.split(r"[，、,。！？!?；;\n]+", text or "") if part.strip()]
    punctuation = len(re.findall(r"[，、,]", text or "")) * .2 + len(re.findall(r"[。！？!?；;]", text or "")) * .45
    minimum = round(spoken / 5 + punctuation, 2) if spoken else 0
    maximum = round(spoken / 3.5 + punctuation, 2) if spoken else 0
    reaction = max(0, float(reaction_pause))
    longest = max(counts, default=0)
    return {"characters": spoken, "longest_sentence": longest, "sentence_characters": counts,
            "speed_range": "标准估算 3.5～5 字/秒", "min_seconds": minimum, "max_seconds": maximum,
            "reaction_seconds": reaction, "required_seconds": round(minimum + reaction, 2),
            "shot_duration": shot_duration,
            "status": "overtime" if minimum + reaction > shot_duration + .001 else "long" if longest > 24 else "ok"}


def total_duration(duration: float, settings: dict[str, Any]) -> float:
    """V2 includes reaction. Legacy production added reaction separately."""
    return float(duration) + (max(0, float(settings.get("reaction_pause") or 0)) if settings.get("timing_schema_version") != 2 else 0)
