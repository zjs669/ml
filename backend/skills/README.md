# backend/skills —— AI 每次调用前必读的技能文档

这个目录里的 Markdown 会在**每一次** AI 调用前被注入提示词。它不参与排盘计算，
只规定「模型该按什么顺序读盘、哪些话不能说」。

加载器是 `app/domains/skills/skillfile.py`，本目录是唯一事实来源（改完即生效，不用重启）。

## 1. 目录结构

```
skills/
├── SKILL.md                    # 全局：所有域都注入（id: common.skill）
├── bazi/
│   ├── SKILL.md                # 域必读（always: true）
│   └── cards/
│       └── bazi.relations.order.v1.md   # 卡片：按触发词追加
├── qimen/
│   ├── SKILL.md
│   └── cards/qimen.plate.order.v1.md
├── ziwei/
│   ├── SKILL.md
│   └── cards/ziwei.palace.order.v1.md
├── bench/SKILL.md              # 评测专用 profile，产品链路不加载
└── <其余 14 个域>/SKILL.md
```

三类文件的区别：

| 类型 | 位置 | 何时注入 |
|---|---|---|
| `global` | 根 `SKILL.md` | 每次调用 |
| `domain` | `<domain>/SKILL.md` | 调用该域时（`always: true` 强制注入） |
| `card` | `<domain>/cards/*.md` | 仅当 `triggers` 命中用户文本，或 `priority` 高到预算允许 |

## 2. front-matter 字段

```yaml
---
id: bazi.skill            # 全局唯一，与文件名无强绑定
domain: bazi              # 必须与目录名一致（global 用 common）
title: 四柱解读技能
version: 1.1.0            # 内容有实质改动时 +1
status: approved          # approved 才会被注入；draft 只给人工复核
always: true              # true = 无条件注入，不受触发词影响
max_chars: 2400           # 本文件截断上限
priority: 100             # 预算不足时的取舍依据，越大越优先
source: 人工整理          # 人工整理 / 题库蒸馏 / 人工整理 + 题库蒸馏
updated: 2026-10-26
---
```

- `always: true` 只给「域必读」用。卡片不要设，否则等于每张都注入。
- `max_chars` 按内容长度设：`bazi`/`ziwei` 内容较长用 2600，`bench` 故意精简用 900，其余 2400。
- 超长时加载器会在 `max_chars` 处截断并追加 `…[截断]`，不会报错——所以宁可写短。

## 3. 预算与选择顺序

```
DEFAULT_BUDGET = 4000 字符（单次调用的技能总预算）
```

`select()` 的挑选顺序：

1. 全局 `SKILL.md`（必选）
2. 当前域的 `SKILL.md`（必选）
3. 卡片：按 `priority` 降序尝试，放不下就跳过（不会截半张卡）
4. 外部技能包（`SKILLS_EXTRA_DIRS`，仅评测 profile 加载）

当前实际占用 760–1387 字符 / 4000，余量充足，暂不需要精简。

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

红线（全站一致）：

- 不判吉凶、不推应期、不给行动建议
- 不出现绝对化措辞（必然 / 一定 / 注定）
- 未实现的能力必须显式说明，不能沉默略过

## 6. 新增一个域的 4 步

```bash
# 1. 建目录与 SKILL.md（照抄同结构域的骨架，改读序与口径）
mkdir -p backend/skills/<domain>
$EDITOR backend/skills/<domain>/SKILL.md

# 2. 需要「按问题类型追加」的经验，再建卡片
mkdir -p backend/skills/<domain>/cards
$EDITOR backend/skills/<domain>/cards/<domain>.<topic>.v1.md

# 3. 校验：加载器能解析、字符数在预算内
cd backend && python -m pytest tests/test_skillfile.py -q

# 4. 人工过一遍渲染结果
cd backend && python -c "from app.domains.skills import skillfile; print(skillfile.render('<domain>'))"
```

## 7. 改完怎么验

```bash
cd backend
python -m pytest tests/test_skillfile.py -q          # 解析、去重、预算
python -m pytest tests/test_reporting_budget.py -q   # 提示词总长度
```

测试会断言：每个 `status: approved` 的文件都能解析、`domain` 与目录一致、
`always` 的域必读在每个域都存在、渲染总长度不超预算。
