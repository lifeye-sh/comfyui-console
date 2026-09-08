#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
short-drama-director 静态自检脚本
用法: python3 check_package.py [skill目录]

检查项:
  1. CR 字节污染 / 孤立 ightarrow / 字面 \r\rightarrow
  2. Markdown 表格行管道平衡
  3. 代码围栏平衡
  4. references 模块数量（应与 SKILL.md 架构一致）
  5. 时长/时间轴一致性（单组 ≤15s 等）
  6. 危险词（默认投喂档应回避）
  7. IP/品牌词（GitHub 公开发布建议去重）
  8. 模块文件完整性（SKILL.md 中列出的文件必须存在）
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent

# 危险词（投喂公开平台前应回避；合规词典中的对照列除外）
DANGER_WORDS = [
    "爆头", "颈动脉", "断子绝孙", "插裆", "血沫", "血雾", "骨碎",
    "碎尸", "毙命", "割喉", "开膛", "打爆眼球", "打断骨头",
]

# IP/品牌词（GitHub 公开版建议技术化；UE5/8K 为技术规格，不在此列）
IP_WORDS = [
    "芬奇", "斯皮尔伯格", "黑泽明", "默奇", "一代宗师", "杀破狼",
    "独孤九剑", "梦想一心", "死神",
]

# 合规词典文件（危险词出现在对照列是合理的）
COMPLIANCE_FILE = "platform-safety-compliance-guide.md"


def check_arrows_and_bytes():
    issues = []
    for p in sorted((ROOT / "references").glob("*.md")):
        b = p.read_bytes()
        s = b.decode("utf-8")
        if b.count(b"\r"):
            crn = b.count(b"\r")
            issues.append(f"[字节] {p.name}: 含 CR 字节 ({crn})")
        orph = s.count("ightarrow") - s.count("\\rightarrow")
        if orph:
            issues.append(f"[字节] {p.name}: 孤立 ightarrow ({orph})")
        if "\\r\\rightarrow" in s or "\\n\\rightarrow" in s:
            issues.append(f"[字节] {p.name}: 字面 \\r\\rightarrow")
    return issues


def check_markdown():
    issues = []
    for p in sorted((ROOT / "references").glob("*.md")):
        lines = p.read_text().splitlines()
        for i, l in enumerate(lines, 1):
            if l.startswith("|") and not l.endswith("|"):
                issues.append(f"[Markdown] {p.name}:{i} 表格行未闭合管道")
        n = p.read_text().count("```")
        if n % 2:
            issues.append(f"[Markdown] {p.name}: 代码围栏不配对 ({n})")
    return issues


def check_module_count():
    skill = (ROOT / "SKILL.md").read_text()
    refs = sorted((ROOT / "references").glob("*.md"))
    # 架构图中声明的数量
    declared = None
    m = re.search(r"系统架构与 (\d+) 大专业规则库", skill)
    if m:
        declared = int(m.group(1))
    issues = []
    if declared and declared != len(refs):
        issues.append(
            f"[架构] SKILL.md 声明 {declared} 个模块，实际 references/ 有 {len(refs)} 个"
        )
    # 架构图中列出的文件是否存在
    for name in re.findall(r"([\w-]+\.md)", skill):
        if name == "SKILL.md":
            continue
        if not (ROOT / "references" / name).exists():
            issues.append(f"[架构] SKILL.md 引用 {name} 但文件不存在")
    return issues


def check_timing():
    issues = []
    for p in sorted((ROOT / "references").glob("*.md")):
        s = p.read_text()
        if "必须" in s and "14 组" in s and "15 组" not in s:
            issues.append(f"[时长] {p.name}: 仍写死 14 组（应 14~15）")
        if re.search(r"单镜 3~5 秒，一组 3~4 镜", s):
            issues.append(f"[时长] {p.name}: 旧单镜/组数公式残留")
    return issues


def check_words():
    issues = []
    for p in sorted((ROOT / "references").glob("*.md")):
        if p.name == COMPLIANCE_FILE:
            continue
        s = p.read_text()
        for w in DANGER_WORDS:
            if w in s:
                issues.append(f"[危险词] {p.name}: 「{w}」（投喂公开平台前请转译或确认）")
    return issues


def check_ip():
    issues = []
    for p in sorted((ROOT / "references").glob("*.md")):
        s = p.read_text()
        for w in IP_WORDS:
            if w in s:
                issues.append(f"[IP词] {p.name}: 「{w}」（公开发布建议技术化）")
    return issues


def main():
    all_issues = []
    for fn in (check_arrows_and_bytes, check_markdown, check_module_count,
               check_timing, check_words, check_ip):
        all_issues.extend(fn())

    if not all_issues:
        print("✅ 全部检查通过，包结构干净。")
        return 0

    print(f"⚠️ 发现 {len(all_issues)} 个问题：")
    for i in all_issues:
        print("  -", i)
    return 1


if __name__ == "__main__":
    sys.exit(main())
