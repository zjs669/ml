"""套餐定义。

MVP 只有三档：免费日额度、单次详版、月度会员（额度池）。
价格一律用「分」存储，避免浮点误差；文案与权益集中在这里，前端只做渲染。
"""

from __future__ import annotations

from dataclasses import dataclass, field

PLAN_VERSION = "plans-2026-01"


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    amount_minor: int
    credits: int
    duration_days: int
    tagline: str
    features: tuple[str, ...] = field(default_factory=tuple)
    purchasable: bool = True

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "amount_minor": self.amount_minor,
            "amount_text": f"{self.amount_minor / 100:.2f} 元",
            "credits": self.credits,
            "duration_days": self.duration_days,
            "tagline": self.tagline,
            "features": list(self.features),
            "purchasable": self.purchasable,
            "plan_version": PLAN_VERSION,
        }


PLANS: dict[str, Plan] = {
    "free": Plan(
        code="free",
        name="免费体验",
        amount_minor=0,
        credits=0,
        duration_days=0,
        tagline="每天 1 次简版 AI 解读，排盘与关系判定不限次",
        features=(
            "完整四柱、藏干、十神、五行加权",
            "刑冲合害关系判定（含 rule_id 与出处）",
            "每天 1 次简版 AI 解读",
            "命盘保存、笔记、文本导出",
        ),
        purchasable=False,
    ),
    "report_once": Plan(
        code="report_once",
        name="单次详版解读",
        amount_minor=1900,
        credits=1,
        duration_days=0,
        tagline="1 次详版解读，额度长期有效",
        features=(
            "详版报告：盘面事实 + 传统解释 + 现实建议分段",
            "逐条引用知识库出处，缺依据处明确标注",
            "额度不过期，随时使用",
        ),
    ),
    "member_month": Plan(
        code="member_month",
        name="月度会员",
        amount_minor=4900,
        credits=30,
        duration_days=30,
        tagline="30 天内 30 次详版解读",
        features=(
            "30 次详版解读额度",
            "优先使用最新技能版本",
            "知识库全文检索与出处详情",
            "报告历史与多格式导出",
        ),
    ),
}


def get_plan(code: str) -> Plan | None:
    return PLANS.get(code)


def list_plans() -> list[Plan]:
    return [PLANS["free"], PLANS["report_once"], PLANS["member_month"]]
