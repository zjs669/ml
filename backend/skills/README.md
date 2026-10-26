# backend/skills —— AI 每次调用前必读的技能文档

这个目录里的 Markdown 会在**每一次** AI 调用前被注入提示词。它不参与排盘计算，
只规定「模型该按什么顺序读盘、哪些话不能说」。

加载器是 `app/domains/skills/skillfile.py`，本目录是唯一事实来源（改完即生效，不用重启）。

## 0. 三种「看起来都是文档」的东西，别混

| 概念 | 位置 | 何时注入 | 能否作为引用 |
|---|---|---|---|
| **任务包** | `backend/app/domains/skills/packages/*.json` + `reporting/prompts/*.txt` | 每次生成报告按 domain/深度选中一份 | 否 |
| **技能文件**（本目录） | `backend/skills/**/*.md` | **每次 AI 调用前必读**（全局 + 领域），卡片按触发词追加 | 否，只影响叙述顺序与自查 |
| **知识库** | MySQL `knowledge_chunks`（源 `docs/知识源/*.md`，`approved`） | 检索命中才注入 | **是**，`citations` 只认 `chunk_id` |

一句话：任务包决定「用哪套模板」，技能文件决定「按什么顺序想」，知识库决定「能引用哪句原文」。

## 1. 目录结构

```
skills/
├── SKILL.md                    # 全局：所有域都注入（id: common.skill）
├── bazi/
│   ├── SKILL.md                # 域必读（always: true）
│   └── cards/
│       └── bazi.relations.order.v1.md   # 卡片：按触发词追加
├── qimen/cards/qimen.plate.order.v1.md
├── ziwei/cards/ziwei.palace.order.v1.md
├── bench/SKILL.md              # 评测专用 profile，产品链路不加载
└── <其余 14 个域>/SKILL.md
```

| 类型 | 位置 | 何时注入 |
|---|---|---|
| `global` | 根 `SKILL.md` | 每次调用 |
| `domain` | `<domain>/SKILL.md` | 调用该域时（`always: true` 强制注入） |
| `card` | `<domain>/cards/*.md` | 仅当 `triggers` 命中用户文本，或 `priority` 高到预算允许 |

## 2. front-matter 字段

```yaml
---
id: bazi.skill            # 全局唯一
domain: bazi              # 必须与目录名一致（global 用 common）
title: 四柱解读技能
version: 1.1.0            # 内容有实质改动时 +1
status: approved          # approved 才会被注入；draft 只给人工复核
always: true              # true = 无条件注入，不受触发词影响
max_chars: 2400           # 本文件截断上限
priority: 100             # 预算不足时的取舍依据，越大越优先
source: 人工整理
updated: 2026-10-26
---
```

- `always: true` 只给「域必读」用。卡片不要设，否则等于每张都注入。
- 超长时加载器在 `max_chars` 处截断并追加 `…[截断]`，不报错 —— 所以宁可写短。

## 3. 预算与选择顺序

`DEFAULT_BUDGET = 4000` 字符（单次调用的技能总预算）。`select()` 的顺序：

1. 全局 `SKILL.md`（必选）
2. 当前域的 `SKILL.md`（必选）
3. 卡片：按 `priority` 降序尝试，放不下就跳过（不会截半张卡）
4. 外部技能包（`SKILLS_EXTRA_DIRS`，仅评测 profile 加载）

当前实际占用 760–1387 字符 / 4000，余量充足。

## 4. 两种 profile

| profile | 加载什么 | 用在哪 |
|---|---|---|
| `product` | 全局 + 域必读 + 卡片 | 报告生成、报告追问 |
| `bench` | `bench/SKILL.md` + 同域卡片 | 题库评测（`scripts/bench_eval`） |

**为什么分开**：评测题问「哪年发生何事」，与产品「不做断语」的人设冲突。
混用会让模型拒答或回避，测出来的是人设而不是判断力。

## 5. 写作规范

每个域的 `SKILL.md` 统一五段：

1. **读序**：先报什么、再报什么，缺一不可的字段写清楚
2. **口径**：本域用哪一种流派、边界值是什么
3. **常见错误**：最容易读错的地方（这一节最值钱）
4. **禁止**：不能出现的表述（吉凶、应期、建议、预测）
5. 可选：**未实现项**（让模型知道哪些不能说，而不是编）

红线（全站一致）：不判吉凶、不推应期、不给行动建议；不出现绝对化措辞；
未实现的能力必须显式说明，不能沉默略过。

## 6. 新增一个域的 4 步

```bash
mkdir -p backend/skills/<domain>
$EDITOR backend/skills/<domain>/SKILL.md          # 照抄同结构域的骨架
mkdir -p backend/skills/<domain>/cards            # 需要按问题类型追加经验时
$EDITOR backend/skills/<domain>/cards/<domain>.<topic>.v1.md

cd backend && python -m pytest tests/test_skillfile.py -q
cd backend && python -c "from app.domains.skills import skillfile; print(skillfile.render('<domain>'))"
```

## 7. 改完怎么验

```bash
cd backend
python -m pytest tests/test_skillfile.py -q          # 解析、去重、预算
python -m pytest tests/test_reporting_budget.py -q   # 提示词总长度
```

测试断言：每个 `approved` 文件都能解析、`domain` 与目录一致、
`always` 的域必读在每个域都存在、渲染总长度不超预算。

## 8. 知识源入库

知识源放在 `docs/知识源/`（按典籍/域分目录），是**运行时数据**不是文档：

```bash
# 本地开发（一次性审核写入）
cd backend
python -m app.domains.knowledge.ingest --approve
python -m app.domains.knowledge.ingest --domain ziwei --dir docs/知识源/ziwei --approve

# 线上必须走审核脚本
python -m scripts.admin approve --all-pending
```

新片段一律 `pending`，**必须审核后才可被检索**。`infra/Dockerfile.backend` 会
`COPY docs/知识源 /docs/知识源` 进镜像，首次启动后手动灌一次。

## 9. 蒸馏与转正

```bash
cd backend
python -m scripts.bench_eval --dataset mingli_bench --file ... --limit 39   # 1) 挖错题
python -m scripts.bench_stats --min-wrong 2                                  # 2) 看反复错的题
python -m scripts.distill_skills --min-samples 2 --dry-run                   # 3) 生成草稿
# 4) 人工复核 _draft/：改 status: approved、去掉 id 里的 draft.
#    关键是把结论合并进 <domain>/SKILL.md，而不是堆一堆碎片
python -m scripts.distill_round                                              # 5) 测 delta
```

`test` 只用来测量，不参与取样；`train` 用来挖错题。

## 10. 外部技能包（taibu）

通过 `SKILLS_EXTRA_DIRS` 只读挂载，加载器只取 `interpretation/<domain>.md`：

```env
SKILLS_EXTRA_DIRS=D:\ref\taibu
SKILLS_EXTERNAL_IN_PRODUCT=false
```

**产品侧默认关**：外部包含吉凶断语，与本站红线冲突。评测时可开，
但校验链仍只认 `chunk_id` 与已触发 `rule_id`，外部卡片写错也会被拦下。
