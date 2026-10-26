# AI 能力升级与蒸馏方案

> **历史归档（2026-10）**：追问 / 紫微扩充 / 密钥加密 / 蒸馏链的决策记录，已完成，不再更新。
> 当前行为以代码为准；技能结构见 [../技能与知识源.md](../技能与知识源.md)。

> 本文对应四项诉求：**追问**、**紫微补星与飞星四化**、**密钥加密**、**题库蒸馏**。
> 四条结论都落到具体文件与接口，能被测试和命令验证，不写「感觉」「应该」。

---

## 1. 现状盘点（改之前）

| 项 | 现状 | 缺口 |
|---|---|---|
| 报告追问 | `POST /charts/{id}/reports` 一次性生成，`ai_reports.report_json` 存 7 个字段 | 没有多轮上下文表、没有追问接口、前端只能重新生成整份 |
| 紫微星曜 | 14 主星 + 14 辅星（左辅右弼…天马），全盘 28 颗 | 无杂曜、无长生十二神 / 博士十二神、只有**生年**四化 |
| 飞星四化 | 只有 `C.SI_HUA[年干]` 一次 | 无宫干四化、无大限四化、无流年四化 |
| 密码 | 用户密码 Argon2id 哈希（`core/security.py`） | 第三方密钥（`LLM_API_KEY`、`SMTP_PASSWORD`）在 `.env` 里是**明文** |
| 模型能力 | 技能包 5 个（bazi 2 / ziwei 1 / liuyao 1 / qimen 1），全部是人工写的提示词 | 没有「从做题中总结出来的经验」这一层，也没有题库评测与蒸馏脚本 |

关于「账号密码没加密」：用户密码从来没有明文落库，库里是 `$argon2id$...`。真正没加密的是**程序自己用的密钥**——模型 API Key 与邮箱 SMTP 授权码。本轮按「密钥静态加密」处理，理由见第 4 节。

---

## 2. 决策

- **D1 追问是同一份报告的延续，不是新报告。**
  追问不重新选技能、不重新检索知识片段、不重新扣额度；它读的是「原报告 + 原盘面事实 + 原报告已引用的片段」，只能在这些材料内回答。这样既不会因为重新检索导致前后矛盾，也避免把「追问」做成绕过额度的手段。成本仍受 `LLM_DAILY_TOTAL_BUDGET` 与每小时限流约束。

- **D2 追问答案同样过校验链，但用更窄的 Schema。**
  `{answer, points[], citations[], uncertainties[], safety_note}`。引用只能来自原报告 `citations_json` 里的 chunk_id；盘面一致性沿用 `DOMAIN_FACT_CHECKS`；禁词扫描完全复用。不合格先重试一次，仍不合格就返回**确定性降级回复**（只复述盘面事实 + 说明无法回答），并在 `status=degraded` 标注。

- **D3 紫微只扩「可核验的安星法」，不引入断语。**
  新增 14 颗杂曜、长生十二神、博士十二神、宫干四化、大限四化、流年四化。全部是「哪颗星/哪个四化落在哪个宫」的事实，不做三方四正、不做格局命名、不做吉凶判断。流派仍锁死 `sanhe_default_v1`，差异写进 `docs/口径说明.md`。

- **D4 密钥加密解决的是「备份/误传/截图泄露」，不是「拿到服务器」。**
  用 Fernet（AES-128-CBC + HMAC-SHA256），密文带 `enc:v1:` 前缀，主密钥只从 `SECRETS_MASTER_KEY` 读；未配置时用 `SECRET_KEY` 经 HKDF 派生（可用但会随 `SECRET_KEY` 轮换失效，启动日志会明确提示）。生产环境若发现明文密钥，`assert_safe_for_production()` 直接失败。

- **D5 蒸馏的产物是「技能卡片」，不是模型权重。**
  每张卡片是带 front-matter 的 Markdown，写清适用条件、思考顺序、常见错误、禁止推断。运行时按 domain + 触发词检索 top-k 注入 prompt。卡片分 `draft` / `approved` 两态，脚本只产 `draft`，必须人工复核后挪进正式目录——这条是红线，防止模型自己总结的错误被当成规则。

- **D6 题库只读本地目录，不在代码里下载。**
  MingLi-Bench / fate-bench / BaziQA / 紫微大规模数据集 / bazi-non-reasoning-10k 的许可证各不相同，且体积可达数十 GB。脚本只做**格式归一化 + 评测 + 蒸馏**，数据由使用者自行取得并放到 `backend/data/bench/<name>/`，该目录已在 `.gitignore`。

---

## 3. R1 追问（后端 + 前端）

### 表 `report_followups`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | bigint PK | |
| `report_id` | bigint FK `ai_reports.id` | `ON DELETE CASCADE` |
| `user_id` | bigint FK `users.id` | `SET NULL` |
| `seq` | int | 同一报告内自增，从 1 开始 |
| `question` | text | 用户原问，≤500 字 |
| `answer_json` | JSON | `{answer, points, citations, uncertainties, safety_note}` |
| `citations_json` | JSON | 实际引用到的片段快照 |
| `validation_json` | JSON | 校验结果（是否降级、致命码） |
| `status` | varchar(20) | `complete` / `degraded` |
| `model_provider` / `model_name` | varchar | 记账用 |
| `input_tokens` / `output_tokens` | int | 记账用 |
| `created_at` | datetime | |

索引：`(report_id, seq)`。

### 接口

- `POST /api/v1/reports/{report_id}/followups` → 201 `FollowupOut`
- `GET  /api/v1/reports/{report_id}/followups` → `FollowupOut[]`

约束：同一报告 ≤ **20 轮**（超出 400 `FOLLOWUP_LIMIT`）；每小时 ≤ 30 次（限流）；不扣额度；日预算耗尽时直接降级且不调模型。

### 提示词

`backend/app/domains/reporting/prompts/followup_v1.txt`。三条硬约束：只答所问、只用给定材料、不新增事实。末尾追加输出契约（与报告同一套写法：把结构重复在用户消息末尾，实测服从度更高）。

---

## 4. R2 紫微补星与飞星四化

### 新增星曜（全部按年支/生月/生时/年干定宫）

| 组 | 星 | 起法 |
|---|---|---|
| 生月系 | 天刑、天姚 | 酉宫起正月，天刑顺、天姚逆 |
| 年支系 | 红鸾、天喜 | 卯宫起子年逆数；天喜为红鸾对宫 |
| 年支系 | 龙池、凤阁 | 辰宫顺数 / 戌宫逆数 |
| 年支系 | 天哭、天虚 | 午宫逆数 / 午宫顺数 |
| 年支系 | 蜚廉 | 申宫起子年顺数 |
| 年支系 | 天德、月德 | 酉宫 / 巳宫起子年顺数 |
| 年支三合 | 华盖、咸池 | 寅午戌→戌/卯，申子辰→辰/酉，巳酉丑→丑/午，亥卯未→未/子 |
| 年支三合 | 孤辰、寡宿 | 亥子丑→寅/戌，寅卯辰→巳/丑，巳午未→申/辰，申酉戌→亥/未 |
| 年支三合 | 破碎 | 子午卯酉→巳，寅申巳亥→酉，辰戌丑未→丑 |

### 长生十二神 / 博士十二神

- 长生十二神：水二局、土五局起申，木三局起亥，金四局起巳，火六局起寅；方向同大限（阳男阴女顺）。
- 博士十二神：禄存宫起博士，方向同大限。

### 飞星四化（三层）

| 层 | 依据 | 字段 |
|---|---|---|
| 生年四化 | 年干 | `transformations`（原有） |
| 宫干四化 | 每宫天干 | `palace_transformations[]`，含 `from_palace / stem / type / star / to_palace` |
| 大限四化 | `review_age` 所在大限宫的天干 | `dayun_transformation` |
| 流年四化 | `review_year` 的年干 | `liunian_transformation`，同时给 `liunian_palace` |

`review_age` / `review_year` 可选。不填就只算前两层，结果页不显示大限/流年栏——**不猜年龄**。

### 前端

`ZiweiBoard.vue` 每宫增加：杂曜行（灰）、长生十二神（左下）、博士十二神（右下）、宫干四化小标（`禄→财帛` 形式）。中宫增加「大限四化 / 流年四化」两行，仅在入参提供时显示。

---

## 5. R3 密钥静态加密

- `app/core/secrets.py`：`encrypt_value()` / `decrypt_value()` / `is_encrypted()` / `mask()`。
- `Settings` 新增 `secrets_master_key`；新增属性 `llm_api_key_value` / `smtp_password_value`，自动解密并兼容历史明文。
- `assert_safe_for_production()` 增加两条：`LLM_API_KEY`、`SMTP_PASSWORD` 非空且未加密 → 启动失败。
- `scripts/encrypt_secrets.py`：读 `.env`，把 `LLM_API_KEY` / `SMTP_PASSWORD` 就地改成 `enc:v1:...`，写回前备份 `.env.bak`，并打印掩码后的前后值（**不打印明文**）。
- 单测：加解密往返、密文不含明文、明文向后兼容、错误主密钥解析失败抛出明确异常、生产自检拦截明文。

---

## 6. R4 题库评测与蒸馏

### 目录约定

```
backend/data/bench/<dataset>/cases.jsonl     # 使用者自行放入，已 gitignore
backend/app/domains/skills/distilled/*.md    # 已复核的技能卡片（会被加载）
backend/app/domains/skills/distilled/_draft/ # 蒸馏产出的草稿（不会被加载）
```

### 归一化格式

```json
{"id":"mingli-0001","domain":"bazi","question":"...","options":["A...","B..."],
 "answer":"B","chart_input":{"birth_datetime":"1990-05-20T12:00:00","timezone":"Asia/Shanghai"},
 "source":"MingLi-Bench","split":"test"}
```

适配器 `scripts/bench/datasets.py` 支持 `mingli_bench` / `fate_bench` / `baziqa` / `generic` 四种字段布局，统一成上面的结构。

### 评测 `scripts/bench_eval.py`

- `--dataset mingli_bench --file data/bench/mingli_bench/cases.jsonl --limit 50 --mode mcq`
- 每题**先检索已审核知识片段**（`knowledge_repo.search`，top-3）再作答；命中率单独统计，
  库不可用时自动退化为无知识作答并在记录里标 `kb_error`。
- 指标：**准确率**、知识库命中率、解析失败率、P50/P95 延迟、token 消耗、按 domain 分组准确率。
- 输出 `docs/模型评测.md`（第二部分·题库）（覆盖生成），同时在终端打印失败样例 id，便于二次蒸馏。
- 每次作答**追加**到 `data/bench/attempts.jsonl`（带 `run_id / timestamp / kb_chunks`），
  不追加就统计不出「同一道题错了几次」。

### 复盘 `scripts/bench_stats.py`

`bench_eval` 是一张快照，复盘要跨轮次：

| 输出 | 用途 |
|---|---|
| 每道题的「错/答」 | 反复错才值得写技能卡，错一次可能只是抖动 |
| 未作答次数（`got` 为空） | 区分「格式失败」与「知识失败」，前者先修提示词 |
| 错误类型分布 | 决定本轮该补肾知识还是补输出约束 |
| 题库缺口 | 评测时因缺题目/选项/答案被跳过的条数（`last_load.json`） |

输出 `docs/题库复盘.md`。

### 蒸馏 `scripts/distill_skills.py`

输入：评测产出的 `attempts.jsonl`（含 `question / answer / verdict / errors / chart_facts`）。
流程：按 `domain + 错误码` 聚类 → 每类取最多 8 条样例 → 调模型产出「这一类题应该按什么顺序看盘、最容易错在哪」→ 写 `_draft/<domain>.<signature>.md`，`status: draft`。
红线：**脚本永不写正式目录**，也不改已有卡片；promotion 必须人工 `git mv` 并改 `status: approved`。

### 运行时注入

`app/domains/skills/distilled.py`：加载 → 按 `domain` 过滤 → 用「触发词命中数 + priority」排序 → 取 top 3。
注入位置在用户消息的「参考经验」段，并明确写：**只能作为组织叙述的顺序，不得作为知识库引用，不得据此新增事实或关系**。这条与校验链不冲突：引用仍只认 `chunk_id`，关系仍只认已触发的 `rule_id`。

---

## 7. 验收门槛

| 项 | 门槛 |
|---|---|
| 后端回归 | `pytest -q` 全绿，新增用例计入总数 |
| 追问 | 20 轮上限生效；引用越界被判死；预算耗尽降级且不调模型；未登录 401 |
| 紫微 | 新增星曜落宫可被单测逐颗核对；四化三层的 `to_palace` 与盘面星位一致；未传 `review_age/year` 时不出空字段 |
| 密钥 | 密文往返一致；`.env` 中不再出现 `sk-`/32 位以上裸密钥；生产自检拦明文 |
| 蒸馏 | 加载器只读 `approved`；注入内容不污染引用与规则校验；草稿不会被加载 |
| 题库 | `bench_eval --limit 5` 可在无网络时以 mock 跑通并产出报告骨架 |
| 前端 | `npm run build`（含 `vue-tsc --noEmit`）零错误 |

---

## 8. 明确不做

- 不做断语、不做择日、不做合婚、不做流年吉凶推演。
- 不做微调（SFT/LoRA）：本仓库只做「题库评测 + 技能蒸馏 + 提示词注入」，权重训练不在此范围。
- 不自动下载第三方数据集（许可证与体积原因）。
- 不做跨报告追问（追问只挂在某一份报告上），也不做追问的分享。
- 不做真实支付网关；支付仍为 Mock 通道。

---

## 9. 实现记录（本轮实际落地）

| 项 | 落地文件 | 验证方式 |
|---|---|---|
| 追问表与接口 | `models/report.py`、`alembic/versions/d3f7a2c9b105_*.py`、`api/v1/reports.py`、`domains/reporting/followup.py`、`schemas/report.py`、`prompts/followup_v1.txt` | `tests/test_followup.py` 7 项；联调实测 201 + 历史列表 200 |
| 追问校验 | `domains/llm/validator.py::validate_followup`、`reporting/coerce.py::normalize_followup` | 引用越界 → fatal；空壳 → schema_invalid |
| 杂曜 / 十二神 | `domains/ziwei/constants.py`、`engine.py::_minor_stars/_life_cycle/_bo_shi` | 12 例手算锚点（华盖戌、咸池卯、孤辰申、破碎巳…） |
| 四化四层 | `engine.py::_transformations_for/_palace_transformations/_dayun_transformation/_liunian_transformation` | 48 条宫干四化逐条与星位对账；2026 → 丙午 |
| 密钥加密 | `core/secrets.py`、`scripts/encrypt_secrets.py`、`config.py` 属性与生产自检 | `tests/test_secrets.py` 9 项；本地 `.env` 中 `LLM_API_KEY` 已是 `enc:v1:` |
| 蒸馏卡 | `domains/skills/distilled.py` + 3 张种子卡（bazi / ziwei / qimen） | `tests/test_distilled_skills.py` 6 项 |
| 题库工具 | `scripts/bench/datasets.py`、`scripts/bench_eval.py`、`scripts/distill_skills.py` | `tests/test_bench_datasets.py` 6 项；mock 下跑通并产出报告骨架 |
| 题库复盘 | `scripts/bench_stats.py`、`bench_eval` 的追加模式与 `last_load.json` | `tests/test_bench_stats.py` 3 项；每道题「错/答」、未作答、题库缺口 |
| MingLi-Bench 接入 | `scripts/bench/mingli.py`（字段映射）、`scripts/prepare_bench.py`（按命例切分）、`scripts/bench/charts.py`（预计算盘面） | 160 题 / 32 命例；排盘 160/160；train 121 / test 39 |
| 首轮实测 | `docs/模型评测-MingLi-Bench.md`、`docs/题库复盘.md`、`_draft/` 两张卡片 | `minimax-m3.1-flash`：r1 30.8%（800 tokens）→ r2 38.5%（1600 tokens），随机基线 25% |
| 四柱流年 | `domains/bazi/engine.py`、`schemas.py`、`BaziBoard.vue` | `tests/test_bazi_liunian.py` 9 项；页面上大运轴 + 10 年流年条 |
| 客户端 | `types.ts`、`api/reports.ts`、`ChartDetailPage.vue`、`ZiweiBoard.vue`、`ZiweiPage.vue` | `npm run build`（含 `vue-tsc --noEmit`）零错误 |

回归：后端 `pytest -q` → **1266 passed, 4 skipped**；前端构建零错误。

首轮评测里发现两件事，已写进 `docs/题库与训练数据.md`：

1. `deepseek-v4.1-flash` 会先写长推理，容易撞 `max_tokens`（1200/4000 都截断），批量评测更适合用输出短的模型；
   所以 `bench_eval` 增加了 `--model` 覆盖，评测与产品配置解耦。
2. 同一批题 800 → 1600 tokens，准确率 30.8% → 38.5%，差额几乎全来自「截断」；
   因此报告必须把「未作答/调用失败」与「选错」分开统计，否则会把格式问题当成智力问题。

两个需要使用者参与的环节：

1. **人工转正蒸馏卡**：`_draft/` 里的内容不会被加载，必须在复核后改成 `approved` 并移出目录；
2. **题库授权与落库**：`backend/data/bench/` 已被 gitignore，数据集需自行取得后放入；脚本不下载、不提交。

---

## 10. 第二轮补充：技能文件 SKILL.md

第一轮的蒸馏产物放在 pp/domains/skills/distilled/，是「命中触发词才注入」的经验卡，
没有「每次必读」的入口。第二轮把它升级为 ackend/skills/：

- 全局与领域 SKILL.md 每次注入，卡片按触发词追加，总预算 4000 字符；
- 报告 / 追问 / 题库评测三个入口共用 skillfile.render()；
- 实际使用的卡片 id 写进 alidation.skills_used，可用 ench_eval --no-skills 做消融。

目录、字段与转正流程见 docs/技能与知识源.md；蒸馏循环见 scripts/distill_round.py。
