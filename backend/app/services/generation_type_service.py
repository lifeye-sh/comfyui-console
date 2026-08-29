"""生成类型服务增强：启用/排序/参数模板修改。"""
from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.comfy.value_normalizers import H3_ASPECT_RATIO_ALIASES, normalize_h3_aspect_ratio
from app.models import Batch, GenerationType, Setting, Task, Workflow, WorkflowVersion

# 默认选择项（存入 settings 表，管理员可在平台设置页修改）
DEFAULT_SELECT_OPTIONS: dict[str, list[dict]] = {
    "image_size": [
        {"label": "横屏 16:9 · 1280×720", "value": "1280x720"},
        {"label": "横屏 16:9 · 1792×1024", "value": "1792x1024"},
        {"label": "横屏 16:9 · 1920×1080", "value": "1920x1080"},
        {"label": "横屏 21:9 · 1792×768", "value": "1792x768"},
        {"label": "横屏 4:3 · 1408×1056", "value": "1408x1056"},
        {"label": "正方形 1:1 · 1024×1024", "value": "1024x1024"},
        {"label": "正方形 1:1 · 1280×1280", "value": "1280x1280"},
        {"label": "竖屏 9:16 · 720×1280", "value": "720x1280"},
        {"label": "竖屏 9:16 · 1024×1792", "value": "1024x1792"},
        {"label": "竖屏 9:16 · 1088×1920", "value": "1088x1920"},
        {"label": "竖屏 3:4 · 1152×1536", "value": "1152x1536"},
    ],
    "video_size": [
        {"label": "16:9 横屏 · 832×480（草稿）", "value": "832x480"},
        {"label": "16:9 横屏 · 1024×576（本地中等显存）", "value": "1024x576"},
        {"label": "16:9 横屏 · 1280×720（通用720P）", "value": "1280x720"},
        {"label": "16:9 横屏 · 1792×1024（电影高清）", "value": "1792x1024"},
        {"label": "16:9 横屏 · 1920×1080（1080P成片）", "value": "1920x1080"},
        {"label": "9:16 竖屏 · 480×832（草稿）", "value": "480x832"},
        {"label": "9:16 竖屏 · 576×1024（本地中等显存）", "value": "576x1024"},
        {"label": "9:16 竖屏 · 720×1280（通用720P）", "value": "720x1280"},
        {"label": "9:16 竖屏 · 1088×1920（32倍数优选）", "value": "1088x1920"},
        {"label": "9:16 竖屏 · 1080×1920（平台标准1080P）", "value": "1080x1920"},
        {"label": "1:1 方形 · 768×768（草稿）", "value": "768x768"},
        {"label": "1:1 方形 · 1024×1024（通用）", "value": "1024x1024"},
        {"label": "1:1 方形 · 1280×1280（高清）", "value": "1280x1280"},
        {"label": "3:4 竖屏 · 768×1024", "value": "768x1024"},
        {"label": "4:3 横屏 · 1024×768", "value": "1024x768"},
        {"label": "21:9 电影超宽屏 · 1280×544", "value": "1280x544"},
        {"label": "21:9 电影超宽屏 · 1792×768", "value": "1792x768"},
    ],
    "image_width": [
        {"label": "512", "value": 512},
        {"label": "720", "value": 720},
        {"label": "768", "value": 768},
        {"label": "1024", "value": 1024},
        {"label": "1280", "value": 1280},
    ],
    "image_height": [
        {"label": "512", "value": 512},
        {"label": "720", "value": 720},
        {"label": "768", "value": 768},
        {"label": "1024", "value": 1024},
        {"label": "1280", "value": 1280},
    ],
    "video_width": [
        {"label": "480", "value": 480},
        {"label": "640", "value": 640},
        {"label": "720", "value": 720},
        {"label": "832", "value": 832},
        {"label": "1080", "value": 1080},
    ],
    "video_height": [
        {"label": "480", "value": 480},
        {"label": "640", "value": 640},
        {"label": "720", "value": 720},
        {"label": "832", "value": 832},
        {"label": "1080", "value": 1080},
    ],
    "video_length": [
        {"label": "33 帧（约1秒）", "value": 33},
        {"label": "49 帧（约2秒）", "value": 49},
        {"label": "81 帧（约3秒）", "value": 81},
        {"label": "121 帧（约5秒）", "value": 121},
        {"label": "161 帧（约7秒）", "value": 161},
    ],
    "video_fps": [
        {"label": "12 fps", "value": 12},
        {"label": "16 fps", "value": 16},
        {"label": "24 fps", "value": 24},
        {"label": "30 fps", "value": 30},
    ],
    "h3_aspect_ratio": [
        {"label": value, "value": value}
        for value in H3_ASPECT_RATIO_ALIASES.values()
    ],
    # 工具类参数选项
    "img2prompt_type": [
        {"label": "自然描述（适合文生图）", "value": "natural"},
        {"label": "详细风格（构图/光影）", "value": "detailed"},
        {"label": "标签化（关键词）", "value": "tags"},
        {"label": "艺术描述（画家视角）", "value": "artistic"},
    ],
}

# 每个类型的固定基础参数模板（ParamSchema 格式）
# width/height/length/fps 使用 select + options_from（从 settings 动态读取选项）
PARAM_TEMPLATES: dict[str, list[dict]] = {
    # ---- 图片生成 ----
    "t2i": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "image_width", "default": 720},
        {"key": "height", "type": "select", "label": "高度", "options_from": "image_height", "default": 1280},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "i2i": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "input_image", "type": "image", "label": "参考图"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "image_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "image_height", "default": 720},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "i2i_2": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "input_image_1", "type": "image", "label": "参考图1"},
        {"key": "input_image_2", "type": "image", "label": "参考图2"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "image_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "image_height", "default": 720},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "i2i_3": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "input_image_1", "type": "image", "label": "参考图1"},
        {"key": "input_image_2", "type": "image", "label": "参考图2"},
        {"key": "input_image_3", "type": "image", "label": "参考图3"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "image_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "image_height", "default": 720},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "mixed": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "sub_type", "type": "select", "label": "子类型", "options": [
            {"label": "文生图", "value": "t2i"},
            {"label": "单图生图", "value": "i2i"},
            {"label": "双图生图", "value": "i2i_2"},
            {"label": "三图生图", "value": "i2i_3"},
        ], "default": "t2i"},
        {"key": "input_image", "type": "image", "label": "参考图"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "image_width", "default": 720},
        {"key": "height", "type": "select", "label": "高度", "options_from": "image_height", "default": 1280},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    # ---- 视频生成 ----
    "t2v": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "video_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "video_height", "default": 720},
        {"key": "length", "type": "select", "label": "帧数", "options_from": "video_length", "default": 81},
        {"key": "fps", "type": "select", "label": "帧率", "options_from": "video_fps", "default": 24},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "i2v": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "input_image", "type": "image", "label": "首帧/参考图"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "video_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "video_height", "default": 720},
        {"key": "length", "type": "select", "label": "帧数", "options_from": "video_length", "default": 81},
        {"key": "fps", "type": "select", "label": "帧率", "options_from": "video_fps", "default": 24},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "start_end": [
        {"key": "prompt", "type": "textarea", "label": "转场提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "first_frame", "type": "image", "label": "首帧"},
        {"key": "last_frame", "type": "image", "label": "尾帧"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "video_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "video_height", "default": 720},
        {"key": "length", "type": "select", "label": "帧数", "options_from": "video_length", "default": 81},
        {"key": "fps", "type": "select", "label": "帧率", "options_from": "video_fps", "default": 24},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "reference": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "negative_prompt", "type": "textarea", "label": "负面提示词"},
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "ref_image", "type": "image", "label": "参考图"},
        {"key": "ref_video", "type": "video", "label": "参考视频"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "video_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "video_height", "default": 832},
        {"key": "length", "type": "select", "label": "帧数", "options_from": "video_length", "default": 81},
        {"key": "fps", "type": "select", "label": "帧率", "options_from": "video_fps", "default": 24},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "digital_human": [
        {"key": "prompt", "type": "textarea", "label": "正向提示词"},
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "ref_image", "type": "image", "label": "参考人物图"},
        {"key": "ref_video", "type": "video", "label": "参考视频"},
        {"key": "audio_1", "type": "audio", "label": "音频1"},
        {"key": "audio_2", "type": "audio", "label": "音频2"},
        {"key": "control_1", "type": "image", "label": "控制素材1"},
        {"key": "control_2", "type": "image", "label": "控制素材2"},
        {"key": "width", "type": "select", "label": "宽度", "options_from": "video_width", "default": 480},
        {"key": "height", "type": "select", "label": "高度", "options_from": "video_height", "default": 720},
        {"key": "length", "type": "select", "label": "帧数", "options_from": "video_length", "default": 81},
        {"key": "fps", "type": "select", "label": "帧率", "options_from": "video_fps", "default": 24},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "motion_transfer": [
        {"key": "frame_rate", "type": "int", "label": "帧率", "default": 24, "min": 1, "max": 120},
        {"key": "frame_load_cap", "type": "int", "label": "加载帧数上限", "default": 0, "min": 0, "help": "0 表示不限制"},
        {"key": "skip_seconds", "type": "float", "label": "跳过秒数", "unit": "秒", "default": 0, "min": 0},
        {"key": "resolution", "type": "select", "label": "分辨率选择", "options": [
            {"label": "480p", "value": 1},
            {"label": "576p（默认）", "value": 2},
            {"label": "720p", "value": 3},
            {"label": "1080p", "value": 4},
        ], "default": 2},
        {"key": "motion_algorithm", "type": "select", "label": "动作算法", "options": [
            {"label": "vitpose", "value": 1},
            {"label": "sdpose", "value": 2},
            {"label": "wuwupose", "value": 3},
        ], "default": 1},
        {"key": "expression_enabled", "type": "bool", "label": "表情开启", "default": False},
        {"key": "expression_strength", "type": "float", "label": "表情强度", "default": 1.0, "min": 0, "max": 2, "step": 0.05},
        {"key": "camera_enabled", "type": "bool", "label": "运镜开启", "default": False},
        {"key": "camera_strength", "type": "float", "label": "运镜强度", "default": 1.0, "min": 0, "max": 2, "step": 0.05},
        {"key": "lora_strength", "type": "float", "label": "Lora强度", "default": 1.0, "min": 0, "max": 2, "step": 0.05},
        {"key": "source_video", "type": "video", "label": "原始视频", "required": True},
        {"key": "target_image", "type": "image", "label": "目标人物图", "required": True},
        {"key": "multi_reference_enabled", "type": "bool", "label": "多参开启", "default": False},
        {"key": "multi_reference_count", "type": "int", "label": "多参图数", "default": 1, "min": 1, "max": 5},
        {"key": "reference_image_1", "type": "image", "label": "多参图1"},
        {"key": "reference_image_2", "type": "image", "label": "多参图2"},
        {"key": "reference_image_3", "type": "image", "label": "多参图3"},
        {"key": "reference_image_4", "type": "image", "label": "多参图4"},
        {"key": "reference_image_5", "type": "image", "label": "多参图5"},
    ],
    "person_replace": [
        {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
        {"key": "source_video", "type": "video", "label": "原始视频", "required": True},
        {"key": "target_image", "type": "image", "label": "目标人物图", "required": True},
        {"key": "prompt", "type": "textarea", "label": "替换要求"},
        {"key": "identity_strength", "type": "float", "label": "身份一致性", "default": 1.0, "min": 0, "max": 2, "step": 0.05},
        {"key": "motion_strength", "type": "float", "label": "动作保留强度", "default": 1.0, "min": 0, "max": 2, "step": 0.05},
        {"key": "preserve_audio", "type": "bool", "label": "保留原音频", "default": True},
    ],
    # ---- 音频生成 ----
    "tts": [
        {"key": "text", "type": "textarea", "label": "待合成文本"},
        {"key": "voice", "type": "select", "label": "说话人", "options": [
            {"label": "默认", "value": "default"},
        ], "default": "default"},
        {"key": "language", "type": "select", "label": "语言", "options": [
            {"label": "中文", "value": "zh"},
            {"label": "英文", "value": "en"},
            {"label": "日文", "value": "ja"},
        ], "default": "zh"},
        {"key": "speed", "type": "float", "label": "语速", "default": 1.0, "min": 0.5, "max": 2.0},
        {"key": "pitch", "type": "float", "label": "音调", "default": 0, "min": -12, "max": 12},
        {"key": "emotion", "type": "select", "label": "情绪", "options": [
            {"label": "中性", "value": "neutral"},
            {"label": "高兴", "value": "happy"},
            {"label": "悲伤", "value": "sad"},
            {"label": "愤怒", "value": "angry"},
        ], "default": "neutral"},
        {"key": "sample_rate", "type": "int", "label": "采样率", "default": 44100},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "music": [
        {"key": "description", "type": "textarea", "label": "音乐描述"},
        {"key": "lyrics", "type": "textarea", "label": "歌词"},
        {"key": "vocal", "type": "bool", "label": "包含人声", "default": False},
        {"key": "duration", "type": "float", "label": "时长", "unit": "秒", "default": 30},
        {"key": "sample_rate", "type": "int", "label": "采样率", "default": 44100},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    "convert": [
        {"key": "source_audio", "type": "audio", "label": "源音频"},
        {"key": "ref_audio", "type": "audio", "label": "参考音色"},
        {"key": "target_voice", "type": "select", "label": "目标音色", "options": [
            {"label": "默认", "value": "default"},
        ], "default": "default"},
        {"key": "strength", "type": "float", "label": "转换强度", "default": 0.8, "min": 0, "max": 1},
        {"key": "sample_rate", "type": "int", "label": "采样率", "default": 44100},
        {"key": "seed", "type": "seed", "label": "随机种子", "random": True},
    ],
    # 工具类（不归入 image/video/audio 分组）：图片反推和中英互译
    "img2prompt": [
        {"key": "input_image", "type": "image", "label": "输入图片", "required": True, "group": "media", "media_order": 1},
        {"key": "prompt_type", "type": "select", "label": "提示词类型", "options_from": "img2prompt_type", "default": "natural"},
        {"key": "max_length", "type": "int", "label": "最大长度", "default": 200, "min": 50, "max": 500},
        {"key": "language", "type": "select", "label": "输出语言", "options": [
            {"label": "中文", "value": "zh"},
            {"label": "英文", "value": "en"},
        ], "default": "zh"},
        {"key": "seed", "type": "seed", "label": "随机种子", "default": 0},
    ],
    "translate": [
        {"key": "input_text", "type": "textarea", "label": "输入文本", "required": True, "default": ""},
        {"key": "source_lang", "type": "select", "label": "源语言", "options": [
            {"label": "自动检测", "value": "auto"},
            {"label": "中文", "value": "zh"},
            {"label": "英文", "value": "en"},
            {"label": "日文", "value": "ja"},
            {"label": "韩文", "value": "ko"},
            {"label": "法语", "value": "fr"},
        ], "default": "auto"},
        {"key": "target_lang", "type": "select", "label": "目标语言", "options": [
            {"label": "中文", "value": "zh"},
            {"label": "英文", "value": "en"},
            {"label": "日文", "value": "ja"},
            {"label": "韩文", "value": "ko"},
            {"label": "法语", "value": "fr"},
        ], "default": "en"},
        {"key": "domain", "type": "select", "label": "领域", "options": [
            {"label": "通用", "value": "general"},
            {"label": "影视/短剧", "value": "drama"},
            {"label": "电商", "value": "ecommerce"},
            {"label": "技术文档", "value": "tech"},
        ], "default": "general"},
        {"key": "preserve_format", "type": "bool", "label": "保留格式/换行", "default": True},
    ],
}

BUILTIN_TYPES = [
    ("image", "t2i", "文生图", 10),
    ("image", "i2i", "单图生图", 11),
    ("image", "i2i_2", "双图生图", 12),
    ("image", "i2i_3", "三图生图", 13),
    ("image", "mixed", "混合生图", 14),
    ("video", "t2v", "文生视频", 20),
    ("video", "i2v", "图生视频", 21),
    ("video", "start_end", "批量首尾帧", 22),
    ("video", "reference", "视频参考", 23),
    ("video", "digital_human", "数字人", 24),
    ("video", "motion_transfer", "动作迁移", 25),
    ("video", "person_replace", "人物替换", 26),
    ("audio", "tts", "文生语音", 30),
    ("audio", "music", "音乐生成", 31),
    ("audio", "convert", "音频转换", 32),
    ("tool", "img2prompt", "图片反推", 40),
    ("tool", "translate", "中英互译", 41),
]

# 选择项维护 key 的标签（供前端设置页显示）
SELECT_OPTION_LABELS: dict[str, str] = {
    "image_size": "图片尺寸",
    "video_size": "视频尺寸",
    "image_width": "图片宽度",
    "image_height": "图片高度",
    "video_width": "视频宽度",
    "video_height": "视频高度",
    "video_length": "视频帧数",
    "video_fps": "视频帧率",
    "h3_aspect_ratio": "H3宽高比",
}

MAINTAINABLE_SELECT_OPTION_KEYS = (
    "image_size", "video_size", "video_length", "video_fps", "h3_aspect_ratio",
)
DEFAULT_SELECT_VALUES: dict[str, int | str] = {
    "image_size": "1088x1920",
    "video_size": "576x1024",
    "video_length": 81,
    "video_fps": 24,
    "h3_aspect_ratio": "16:9 (Widescreen)",
}

MOTION_TRANSFER_SCHEME_KEY = "motion_transfer_parameter_schemes"
CUSTOM_SELECT_OPTION_DEFINITIONS_KEY = "custom_select_option_definitions"
MOTION_TRANSFER_SCHEME_DEFAULTS = [{
    "id": 1,
    "name": "默认方案",
    "is_default": True,
    "params": {
        "frame_rate": 24, "frame_load_cap": 0,
        "resolution": 2, "motion_algorithm": 1,
        "expression_enabled": False, "expression_strength": 1.0,
        "camera_enabled": False, "camera_strength": 1.0, "lora_strength": 1.0,
    },
}]


def get_motion_transfer_schemes(db: Session) -> list[dict]:
    setting = db.get(Setting, MOTION_TRANSFER_SCHEME_KEY)
    return setting.value if setting and setting.value else MOTION_TRANSFER_SCHEME_DEFAULTS


def save_motion_transfer_schemes(db: Session, schemes: list[dict]) -> list[dict]:
    if schemes and not any(item.get("is_default") for item in schemes):
        schemes[0]["is_default"] = True
    default_seen = False
    for item in schemes:
        if item.get("is_default"):
            item["is_default"] = not default_seen
            default_seen = True
    setting = db.get(Setting, MOTION_TRANSFER_SCHEME_KEY)
    if setting:
        setting.value = schemes
    else:
        db.add(Setting(key=MOTION_TRANSFER_SCHEME_KEY, value=schemes))
    db.commit()
    return schemes


def normalize_param_template(value: Any, code: str | None = None) -> list[dict]:
    """Normalize legacy JSON shapes to the parameter array used by V1 and V2."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        parameters = value.get("parameters")
        if isinstance(parameters, list):
            return [item for item in parameters if isinstance(item, dict)]
        if value.get("key") and value.get("type"):
            return [value]
        if value and all(isinstance(item, dict) for item in value.values()):
            return list(value.values())
    return [dict(item) for item in PARAM_TEMPLATES.get(code or "", [])]


def repair_param_templates(db: Session) -> int:
    """Persistently repair old `{}`/mapping values so downstream task code is safe."""
    repaired = 0
    for item in db.query(GenerationType).all():
        normalized = normalize_param_template(item.param_template, item.code)
        if item.param_template != normalized:
            item.param_template = normalized
            repaired += 1
    if repaired:
        db.commit()
    return repaired


def list_types(db: Session, media_type: Optional[str] = None, enabled_only: bool = False) -> list[GenerationType]:
    q = db.query(GenerationType).filter(GenerationType.deleted_at.is_(None))
    if media_type:
        q = q.filter(GenerationType.media_type == media_type)
    if enabled_only:
        q = q.filter(GenerationType.enabled.is_(True))
    items = q.order_by(GenerationType.menu_order).all()
    for item in items:
        item.param_template = normalize_param_template(item.param_template, item.code)
    return items


def set_default_workflow(db: Session, gt: GenerationType, workflow_version_id: int) -> GenerationType:
    v = db.get(WorkflowVersion, workflow_version_id)
    if not v:
        raise ValueError("工作流版本不存在")
    workflow = db.get(Workflow, v.workflow_id)
    if not workflow or workflow.generation_type_id != gt.id:
        raise ValueError("只能将当前生成类型自己的工作流设为默认")
    gt.default_workflow_id = v.workflow_id
    db.commit()
    db.refresh(gt)
    return gt


def patch_type(db: Session, gt: GenerationType, param_template: Optional[list[dict]], enabled: Optional[bool], menu_order: Optional[int]) -> GenerationType:
    if param_template is not None:
        gt.param_template = normalize_param_template(param_template, gt.code)
    if enabled is not None:
        gt.enabled = enabled
    if menu_order is not None:
        gt.menu_order = menu_order
    db.commit()
    db.refresh(gt)
    return gt


def has_task_history(db: Session, generation_type_id: int) -> bool:
    """Treat every task row, including a draft, as usage history."""
    return db.query(Task.id).join(Batch, Batch.id == Task.batch_id).filter(or_(
        Task.generation_type_id == generation_type_id,
        Batch.generation_type_id == generation_type_id,
    )).first() is not None


def can_delete_type(db: Session, generation_type: GenerationType) -> bool:
    return (
        generation_type.deleted_at is None
        and not generation_type.enabled
        and not has_task_history(db, generation_type.id)
    )


def seed_builtin_types(db: Session) -> None:
    existing = {t.code for t in db.query(GenerationType).all()}
    added = False
    for media_type, code, name, order in BUILTIN_TYPES:
        if code in existing:
            # Seed data is only a bootstrap default. Existing rows may contain
            # administrator-managed parameter designs and must never be reset
            # when Uvicorn reloads or the service restarts.
            continue
        db.add(GenerationType(
            media_type=media_type,
            code=code,
            name=name,
            menu_order=order,
            param_template=PARAM_TEMPLATES.get(code, []),
        ))
        added = True
    if added:
        db.commit()
    repair_param_templates(db)


def seed_select_options(db: Session) -> None:
    """初始化选择项默认值到 settings 表。"""
    for key, options in DEFAULT_SELECT_OPTIONS.items():
        existing = db.get(Setting, key)
        if existing:
            if key == "h3_aspect_ratio" and isinstance(existing.value, list):
                repaired = []
                changed = False
                for item in existing.value:
                    if not isinstance(item, dict):
                        repaired.append(item)
                        continue
                    repaired_item = dict(item)
                    normalized = normalize_h3_aspect_ratio(repaired_item.get("value"))
                    if normalized != repaired_item.get("value"):
                        repaired_item["value"] = normalized
                        changed = True
                    repaired.append(repaired_item)
                if changed:
                    # Assign a new list so SQLAlchemy reliably persists JSON changes.
                    existing.value = repaired
            continue
        db.add(Setting(key=key, value=options))
    for key, value in DEFAULT_SELECT_VALUES.items():
        default_key = f"{key}_default"
        existing_default = db.get(Setting, default_key)
        if not existing_default:
            db.add(Setting(key=default_key, value=value))
        elif key == "h3_aspect_ratio":
            normalized = normalize_h3_aspect_ratio(existing_default.value)
            if normalized != existing_default.value:
                existing_default.value = normalized
    db.commit()


def get_select_options(db: Session, key: str) -> list[dict]:
    """从 settings 读取选择项；不存在则返回默认。"""
    s = db.get(Setting, key)
    if s:
        return s.value or []
    return DEFAULT_SELECT_OPTIONS.get(key, [])


def get_custom_select_option_definitions(db: Session) -> list[dict]:
    setting = db.get(Setting, CUSTOM_SELECT_OPTION_DEFINITIONS_KEY)
    value = setting.value if setting else []
    if not isinstance(value, list):
        return []
    return [
        item for item in value
        if isinstance(item, dict) and str(item.get("key", "")).startswith("custom_")
    ]


def get_select_option_definitions(db: Session) -> list[dict]:
    builtins = [{
        "key": key,
        "label": SELECT_OPTION_LABELS.get(key, key),
        "value_type": "string" if isinstance(DEFAULT_SELECT_VALUES.get(key), str) else "number",
        "custom": False,
    } for key in MAINTAINABLE_SELECT_OPTION_KEYS]
    return builtins + get_custom_select_option_definitions(db)


def create_select_option_project(db: Session, label: str, value_type: str = "string") -> dict:
    name = label.strip()
    if not name:
        raise ValueError("项目名称不能为空")
    if value_type not in {"string", "number"}:
        raise ValueError("选项值类型只能是文本或数字")
    definitions = get_custom_select_option_definitions(db)
    if any(item.get("label") == name for item in definitions):
        raise ValueError("已存在同名选择项项目")
    definition = {
        "key": f"custom_{uuid4().hex[:12]}",
        "label": name,
        "value_type": value_type,
        "custom": True,
    }
    definitions.append(definition)
    setting = db.get(Setting, CUSTOM_SELECT_OPTION_DEFINITIONS_KEY)
    if setting:
        setting.value = definitions
    else:
        db.add(Setting(key=CUSTOM_SELECT_OPTION_DEFINITIONS_KEY, value=definitions))
    db.add(Setting(key=definition["key"], value=[]))
    db.commit()
    return definition


def delete_select_option_project(db: Session, key: str) -> None:
    definitions = get_custom_select_option_definitions(db)
    if not any(item.get("key") == key for item in definitions):
        raise ValueError("只能删除自定义选择项项目")
    setting = db.get(Setting, CUSTOM_SELECT_OPTION_DEFINITIONS_KEY)
    if setting:
        setting.value = [item for item in definitions if item.get("key") != key]
    options = db.get(Setting, key)
    default = db.get(Setting, f"{key}_default")
    if options:
        db.delete(options)
    if default:
        db.delete(default)
    db.commit()


def is_select_option_project(db: Session, key: str) -> bool:
    return key in MAINTAINABLE_SELECT_OPTION_KEYS or any(
        item.get("key") == key for item in get_custom_select_option_definitions(db)
    )


def get_all_select_options(db: Session) -> dict[str, list[dict]]:
    """返回所有选择项（供前端设置页和菜单接口使用）。"""
    out: dict[str, list[dict]] = {}
    for definition in get_select_option_definitions(db):
        key = definition["key"]
        out[key] = get_select_options(db, key)
    return out


def get_select_default(db: Session, key: str) -> int | str | None:
    setting = db.get(Setting, f"{key}_default")
    return setting.value if setting else DEFAULT_SELECT_VALUES.get(key)


def save_select_options(db: Session, key: str, options: list[dict], default_value: int | str | None = None) -> None:
    if key == "h3_aspect_ratio":
        options = [
            {**item, "value": normalize_h3_aspect_ratio(item.get("value"))}
            for item in options
        ]
        default_value = normalize_h3_aspect_ratio(default_value)
    s = db.get(Setting, key)
    if s:
        s.value = options
    else:
        db.add(Setting(key=key, value=options))
    values = [item.get("value") for item in options]
    if default_value is not None:
        if default_value not in values:
            raise ValueError("默认值必须是当前选项之一")
        default_key = f"{key}_default"
        default_setting = db.get(Setting, default_key)
        if default_setting:
            default_setting.value = default_value
        else:
            db.add(Setting(key=default_key, value=default_value))
    db.commit()


def menu_tree(db: Session) -> dict:
    """输出菜单结构，options_from 的参数自动填充 settings 里的选项。"""
    select_options = get_all_select_options(db)
    out: dict[str, list[dict]] = {}
    for t in list_types(db, enabled_only=True):
        param_schema: list = []
        if t.default_workflow_id:
            wf = db.get(Workflow, t.default_workflow_id)
            if wf and wf.current_version_id:
                v = db.get(WorkflowVersion, wf.current_version_id)
                if v:
                    param_schema = v.param_schema or []
        if not param_schema:
            param_schema = normalize_param_template(t.param_template, t.code)
        if t.media_type == "video" and t.code != "motion_transfer" and not any(p.get("key") == "duration" for p in param_schema):
            param_schema = [
                *param_schema,
                {"key": "duration", "type": "int", "label": "视频时长（建议单次≤15秒）", "unit": "秒", "default": 5, "min": 1, "max": 600},
            ]
        # 把 options_from 解析成实际 options
        resolved = []
        for p in param_schema:
            item = dict(p)
            if item.get("options_from"):
                item["options"] = select_options.get(item["options_from"], [])
                configured_default = get_select_default(db, item["options_from"])
                if configured_default is not None:
                    item["default"] = configured_default
            resolved.append(item)
        out.setdefault(t.media_type, []).append({
            "code": t.code,
            "name": t.name,
            "id": t.id,
            "media_type": t.media_type,
            "default_workflow_id": t.default_workflow_id,
            "menu_order": t.menu_order,
            "param_template": normalize_param_template(t.param_template, t.code),
            "param_schema": resolved,
            "size_options": select_options.get(f"{t.media_type}_size", []),
            "size_default": get_select_default(db, f"{t.media_type}_size"),
        })
    return out


def get_type_by_code(db: Session, code: str) -> Optional[GenerationType]:
    return db.query(GenerationType).filter(
        GenerationType.code == code,
        GenerationType.deleted_at.is_(None),
    ).first()
