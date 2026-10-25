# `_draft/`：蒸馏草稿（不会生效）

这个目录里的卡片由 `python -m scripts.distill_skills` 生成，`status: draft`。

`backend/app/domains/skills/skillfile.py` **只加载上级目录里的 `SKILL.md` 与 `cards/*.md`，且要求 `status: approved`；
`_draft/` 整个目录不参与加载**，所以这里的文件不会被注入任何提示词。

转正流程：

1. 人读一遍，确认没有编造规则、触发词不过宽、只讲顺序不讲结论；
2. 优先合并进 `backend/skills/<domain>/SKILL.md`（技能文件宜少不宜多）；需要单独检索时再放进 `cards/`；
3. 改 `status: approved`、去掉 `id` 里的 `draft.` 前缀；
4. 跑 `pytest tests/test_skillfile.py`，再用 `scripts.distill_round --no-distill` 对比「带卡/无卡」。

> 为什么要留这道闸门：模型总结出来的「经验」一旦直接生效，等于让模型给自己定规则。
> 总结错一次，后面每份报告都会沿用。
