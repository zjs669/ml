"""性格问卷题库接口。

为什么单独开一个端点而不是塞进 /meta：题库有 40 条、带题干与选项，
每次进 /meta 都带上会让「关于」页多传 10 KB 无关数据。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domains.mbti import items as K

router = APIRouter(prefix="/mbti", tags=["mbti"])


@router.get("/questions")
def questions() -> dict:
    """返回题库与维度定义。前端据此渲染问卷，不在 Vue 里硬编码题目。"""
    return {
        "bank_version": K.BANK_VERSION,
        "dimensions": [
            {
                "dimension": dim,
                "name": K.DIMENSION_LABELS[dim]["name"],
                "poles": {
                    pole_a: K.DIMENSION_LABELS[dim][pole_a],
                    pole_b: K.DIMENSION_LABELS[dim][pole_b],
                },
            }
            for dim, pole_a, pole_b in K.DIMENSIONS
        ],
        "questions": [
            {
                "id": item.id,
                "dimension": item.dimension,
                "text": item.text,
                "option_a": item.option_a,
                "option_b": item.option_b,
            }
            for item in K.QUESTIONS
        ],
        "school_note": K.SCHOOL_NOTE,
    }
