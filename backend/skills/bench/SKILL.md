---
id: bench.skill
domain: bench
title: 题库作答技能
version: 1.1.0
status: approved
always: true
max_chars: 900
priority: 100
source: 人工整理（第 3 轮精简：去掉未经核验的类目经验）
updated: 2026-10-25
---

这是内部题库评测：**必须从 A/B/C/D 选一项**，不允许拒答、不允许写「无法判断」。

1. 先定时间：题干年份 → 找该年流年与所属大运；年龄 → 换算虚岁；「大限」→ 找那一步大运。
2. 再用时间范围排除选项，剩下 2 个以内时，按盘面事实（十神、冲合刑害、宫位）比较。
3. 盘面已给出，不得重排、不得引入盘外信息；若没有一个完全符合，选最接近的一项。
4. 只输出 `{"answer": "B", "confidence": 0.0, "reason": "不超过 80 字"}`。
