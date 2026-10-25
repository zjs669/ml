"""面相 / 手相的提示词与分析类型。

**这些文案全部自写**，不复制任何 AGPL 项目的内容。产品思路（按部位拆分分析类型）
是通用做法，不受版权保护；但具体措辞、JSON schema、免责声明必须自有。

三条硬约束写进每一份提示词：
1. 只描述「图像上可见的形态」，不推断性格、命运、健康；
2. 不给吉凶结论、不给事件预测、不评价外貌美丑；
3. 不确定的地方必须写进 `uncertainties`，不许补全。

输出 schema 与报告管线共用同一套 7 字段契约（见 reporting/service.py 的 OUTPUT_CONTRACT），
因此这里不再重复定义结构，只描述「填什么」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AnalysisType:
    id: str
    name: str
    description: str
    #: 该类型关注的图像区域（写进提示词，减少模型自由发挥）
    focus: str


FACE_TYPES: tuple[AnalysisType, ...] = (
    AnalysisType("full", "综合观察", "按三庭五眼逐区描述可见形态", "整体面部比例、三庭（上中下）、五眼（横向五等分）"),
    AnalysisType("forehead", "上庭（额）", "只描述额头区域的形态特征", "额宽、额高、发际线形状、额面平整度"),
    AnalysisType("eyes", "眼区", "只描述眼部与眉部的可见形态", "眼型、眼角走向、双眼间距、眉形与眉距"),
    AnalysisType("nose", "鼻区", "只描述鼻部的可见形态", "鼻梁直曲、鼻头形状、鼻翼宽窄、鼻长比例"),
    AnalysisType("mouth", "口区", "只描述口唇与下颌的可见形态", "唇厚薄、唇形、嘴角走向、下颌轮廓"),
    AnalysisType("cheek", "颧颊区", "只描述颧骨与面颊的可见形态", "颧骨高低、面颊饱满度、下颌角"),
)

PALM_TYPES: tuple[AnalysisType, ...] = (
    AnalysisType("full", "综合观察", "按掌型、三大主线、掌丘逐项描述", "掌型、生命线、智慧线、感情线、主要掌丘"),
    AnalysisType("lines", "掌纹主线", "只描述三大主线的走向与深浅", "生命线、智慧线、感情线的起点、走向、分叉"),
    AnalysisType("mounts", "掌丘", "只描述各掌丘的隆起程度", "金星丘、木星丘、土星丘、太阳丘、水星丘、月丘"),
    AnalysisType("shape", "掌型与指型", "只描述手掌与手指的比例形态", "掌宽掌长比、指长比例、指节粗细"),
)

HAND_TYPES: dict[str, str] = {"left": "左手", "right": "右手"}

FACE_DISCLAIMER = (
    "本页只依据照片上可见的形态做描述性整理，属于传统文化研习内容，"
    "不构成性格判断、命运预测、健康诊断或任何专业意见。"
    "照片仅用于本次分析，按留存策略定期删除。"
)

PALM_DISCLAIMER = (
    "本页只依据照片上可见的掌纹与掌型做描述性整理，属于传统文化研习内容，"
    "不构成性格判断、命运预测、健康诊断或任何专业意见。"
    "照片仅用于本次分析，按留存策略定期删除。"
)

_SHARED_RULES = """\
你必须遵守的三条规则：
1. 只描述图像上**确实可见**的形态。看不见、看不清、被遮挡、光线不足的部分，
   一律写进 uncertainties，不要用「通常」「一般来说」补全。
2. 不做任何推断性结论：不推断性格、智力、健康、寿命、命运、财富、婚姻、事业成败，
   也不评价外貌美丑。observations 里只允许出现形态描述。
3. 传统术数里的对应说法如果要提，必须放在 traditional_interpretations，
   并在 school_note 里写明「属传统说法，无实证依据」。
"""


def _type_block(types: tuple[AnalysisType, ...], analysis_type: str) -> AnalysisType:
    for item in types:
        if item.id == analysis_type:
            return item
    raise ValueError(f"未知分析类型「{analysis_type}」，可用：{'、'.join(t.id for t in types)}")


def build_face_system_prompt(analysis_type: str) -> str:
    target = _type_block(FACE_TYPES, analysis_type)
    return f"""你是传统面相文化的整理助手，本次任务是「{target.name}」。

本次只关注：{target.focus}。

{_SHARED_RULES}
4. 涉及人脸图像时，不得输出任何可用于身份识别的描述（不描述姓名、年龄数字、种族、
   身份、职业等可识别信息），只描述几何形态与纹理。
"""


def build_face_user_prompt(analysis_type: str, question: str | None) -> str:
    target = _type_block(FACE_TYPES, analysis_type)
    extra = f"\n用户的补充问题：{question.strip()}" if question and question.strip() else ""
    return f"""请按「{target.name}」这一分析类型，对随附照片做描述性整理。

要求：
- observations 逐条列出可见形态，每条只写一个观察，不带评价词；
- traditional_interpretations 只放传统说法，并逐条标注 school_note；
- 没有可靠依据的部分写进 uncertainties；
- safety_note 必须包含「本内容不构成任何专业建议」这一层意思。{extra}
"""


def build_palm_system_prompt(analysis_type: str) -> str:
    target = _type_block(PALM_TYPES, analysis_type)
    return f"""你是传统手相文化的整理助手，本次任务是「{target.name}」。

本次只关注：{target.focus}。

{_SHARED_RULES}
4. 掌纹会随年龄、劳作、拍摄角度变化，同一只手不同时期的照片可能不一致；
   这一点必须写进 uncertainties，不能当作稳定特征。
"""


def build_palm_user_prompt(analysis_type: str, hand_type: str, question: str | None) -> str:
    target = _type_block(PALM_TYPES, analysis_type)
    hand = HAND_TYPES.get(hand_type, "未知手别")
    extra = f"\n用户的补充问题：{question.strip()}" if question and question.strip() else ""
    return f"""请按「{target.name}」这一分析类型，对随附的{hand}照片做描述性整理。

要求：
- observations 逐条列出可见形态（起点、走向、分叉、深浅），不带评价词；
- traditional_interpretations 只放传统说法，并逐条标注 school_note；
- 拍摄角度、光线、清晰度导致的不可判读部分写进 uncertainties；
- safety_note 必须包含「本内容不构成任何专业建议」这一层意思。{extra}
"""


def generate_face_title(analysis_type: str) -> str:
    target = _type_block(FACE_TYPES, analysis_type)
    return f"面相观察 · {target.name}"


def generate_palm_title(analysis_type: str, hand_type: str) -> str:
    target = _type_block(PALM_TYPES, analysis_type)
    return f"手相观察 · {target.name}（{HAND_TYPES.get(hand_type, '未知手别')}）"


FaceTypeId = Literal["full", "forehead", "eyes", "nose", "mouth", "cheek"]
PalmTypeId = Literal["full", "lines", "mounts", "shape"]
