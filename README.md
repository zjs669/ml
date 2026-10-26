# 玄枢国学研习台（MVP）

把传统术数拆成**可核验的事实**与**可追溯的解释**：

> 确定性引擎算事实 → 规则引擎判关系 → 知识库检索 → AI 只做解释 → 服务端校验引用与事实 → 存档与额度结算

当前已把同一闭环复用到 **16 个域**：四柱八字、紫微斗数（含运限/飞星）、六爻、奇门遁甲、黄历、小六壬、梅花易数、大六壬、太乙九星、塔罗、西洋占星、关系合盘、性格问卷、解梦，以及面相/手相两个视觉域。真实支付网关、向量检索、微调仍推迟。

---

## 1. 本期能做什么

| 能力 | 说明 |
| --- | --- |
| 排盘 | 公历输入 → 四柱（含纳音/旬空/地势/自坐/神煞）、藏干、十神、五行加权、大运、**流年窗口**（干支/十神/虚岁/所属大运）、节气交节时刻与临界提示 |
| 多术数 | 16 个域共用同一套 `ChartResult` 外壳、报告管线与校验链；每个域只实现一种口径并在结果页回显。清单以 `GET /api/v1/meta/domains` 为唯一事实来源 |
| 紫微 | 14 主星 + 14 辅星 + 16 杂曜 + 长生/博士/将前/岁前十二神，四化分生年/宫干/大限/流年四层，另有小限、流年表、三方四正与飞星串联；**运限**叠六层时间（大限→小限→流年→流月→流日→流时）；**飞星**支持三类定向查询 |
| 新增确定性域 | 黄历（通书日级条目）、小六壬（六宫递推）、梅花易数（六种起卦 + 互错综变 + 体用）、大六壬（月将加时 + 四课 + 贼克法三传）、太乙九星（四层九星观测）、塔罗（78 张无放回 + 9 种牌阵）、西洋占星（日月 + 上升/天顶 + 整宫制）、关系合盘（复用 66 条规则）、性格问卷（自编 40 题）、解梦（意象词表） |
| 视觉分析 | 面相 / 手相：上传图片 → 剥 EXIF → 视觉模型 → 结构化观察。需登录、按次计费、失败全额退回；未配置视觉模型时返回 503 而**不回落文本模型** |
| 四柱反查 | 给定任意几柱 + 年份范围，反查公历日期与时窗；与 `calculate()` 严格互逆（500 例往返测试锁死），候选可一键保存并生成解读 |
| 关系 | **66 条**规则：三会/三合/六合/半会/六冲/三刑/相刑/自刑/相害/相破/天干五合/天干相冲/天干相克，每条带 `rule_id` 与来源，**只报触发不报吉凶** |
| 口径 | `year_boundary` / `day_boundary` / `solar_time` / `school` 四项可选，结果回显并随命盘存档 |
| 知识库 | `knowledge_sources` + `knowledge_chunks`，MySQL ngram 全文检索，只返回已审核条目 |
| 技能库 | `skill_versions` 版本化发布，禁止覆盖旧版本 |
| AI 报告 | Provider Adapter（默认 Mock，可切 OpenAI 兼容真实模型）+ Schema 校验 + 引用存在性 + 事实一致性（按 domain 分派）+ 禁词扫描 + 一次受控重试 + 降级模板 |
| 报告追问 | `POST /reports/{id}/followups`：只依据「原报告 + 原盘面 + 原引用」续答，复用同一套校验链；同一报告 ≤ 20 轮，不扣额度但受限流与日预算约束；不合格时返回确定性降级回复 |
| 调用治理 | `llm_calls` 逐次记账（provider / model / 延迟 / token / 成本 / 错误码，不记提示词与占位原文）+ 当日调用预算熔断 + `/meta/llm-status` 与报告页模型徽章 |
| 账号资产 | 匿名排盘、注册登录、**忘记密码（一次性令牌）**、命盘保存、笔记、报告历史、文本导出、分享链接、删除记录与账号 |
| 账号安全 | Argon2id 存储 + 登录自动 rehash；JWT 强制校验 `iss/aud`；refresh 服务端轮换与重放检测；按账号失败锁定；登出/改密即刻全端下线 |
| 计费 | 每日免费额度 + 单次/会员套餐 + 三态账本（预扣/结算/退还）+ Mock 支付回调 + 幂等；`/billing/config` 公开当前支付模式与可用通道 |
| 合规 | 隐私政策、用户协议、AI 使用说明、退款说明、投诉入口；AI 生成内容显式标识 |

**明确不做**：真实支付网关、向量检索、微调、Web 运营后台（用 CLI 代替）、分享激励；六爻的断语与应期、奇门的择日与法术奇门、置闰法与飞盘奇门、紫微的格局吉凶。

**各域已知边界**（都在结果页的 `warnings` 里写明，不静默省略）：

- 大六壬实现九宗门中的六类取传法（贼克/比用/涉害/遥克/伏吟/返吟），
  昴星、别责、八专未实现，未实现比例约 12.5%；
- 太乙只做九星观测，七十二局、主客算、大小将、十六神未实现；
- 西洋占星只算太阳与月亮，十行星、交点、莉莉丝、Placidus 等宫制未实现
  （`pyswisseph` 需要 MSVC 编译，本机装不上；未实现项通过 `unavailable` 显式列出）；
- 性格问卷为自编 40 题精简版，非官方 MBTI 量表；
- 新域知识源按典籍归属归档（紫微运限/飞星归紫微、合盘归四柱），检索时做父域映射。

## 2. 目录结构

```
backend/
  app/
    core/               config / db / errors / logging / security / ratelimit
    api/v1/             auth charts reports knowledge billing me feedback meta reverse vision mbti
    domains/
      calendar_core/    儒略日、甲子、节气（Meeus + lunar-python 双源）、真太阳时、太阳视黄经
      bazi/             四柱引擎、藏干、十神、五行、大运、反查（reverse.py）
      ziwei/            紫微斗数 sanhe_default_v1（安星法、杂曜、长生/博士十二神、四层四化、飞星串联）
      ziwei_horoscope/  紫微运限：六层时间叠在本命盘上（斗君法起流月）
      ziwei_flying/     紫微飞星：三类定向查询，复用本命盘宫干四化
      liuyao/           六爻 jingfang_najia_v1 + 64 卦常量（hexagrams.py）
      qimen/            奇门遁甲 chaibu_zhuanpan_v1（时家转盘拆补）
      almanac/          黄历：通书日级条目（条目取自 lunar-python）
      xiaoliuren/       小六壬：六宫递推
      meihua/           梅花易数：六种起卦 + 互错综变 + 体用（复用 liuyao 卦表）
      daliuren/         大六壬：月将加时 + 天地盘 + 四课 + 贼克法三传
      taiyi/            太乙九星：四层九星观测
      tarot/            塔罗：78 张牌无放回抽取 + 9 种牌阵
      astrology/        西洋占星（简化）：日月黄经 + 上升/天顶 + 整宫制
      hepan/            关系合盘：复用 relations 规则判定跨盘与盘内
      mbti/             性格问卷：自编 40 题四维计分
      dream/            解梦：意象词表匹配
      vision/           面相 / 手相：提示词 + 分析编排（无确定性算法）
      registry.py       术数注册表：domain → 入参模型 + 计算函数 + kind + schools
      relations/        规则 YAML + 规则引擎（支持自定义位置名以复用跨盘判定）
      knowledge/        ingest 与检索
      skills/           任务包（packages）+ SKILL.md 加载器（skillfile）
      llm/              Provider 抽象、Mock、OpenAI 兼容（含视觉多模态）、validator
      reporting/        报告编排、提示词、降级模板
      billing/          plans / ledger / orders / webhooks
    services/           media.py（MIME 校验 / 剥 EXIF / 内容寻址 / 留存期清理）、export.py
    models/ schemas/ repositories/
  alembic/              5 条迁移（init → llm_calls → auth_tokens → report_followups → chart_media）
  tests/                1650+ 项：16 域引擎、跨域报告链路、反查往返、追问、技能注入、架构守卫、JWT 攻击面、并发与幂等
  scripts/              crosscheck、smoke_api、smoke_e2e（15 域）、prepare_bench、bench_eval、bench_stats、distill_skills、distill_round、encrypt_secrets、admin/*
  data/bench/           本地题库与错例集（体积大、许可证各异，已 gitignore）
  skills/               每次 AI 调用前必读的 SKILL.md（全局 + 16 域）
frontend/
  src/api/              axios 封装、domains/mbti/vision 三个新客户端
  src/api/types/        契约类型按域拆分（common/bazi/reverse/ziwei/liuyao/qimen/charts/reports/knowledge/billing/auth）
  src/config/           domainForms.ts：8 个同构域的声明式表单配置
  src/stores/           auth / chart / usage
  src/components/       chart（含 GenericBoard 兜底）/ report / common
  src/pages/            28 个页面（含 10 个薄页面 + 问卷页 + 合盘页 + 两个视觉页）
  src/router/ src/styles/
infra/                  docker-compose.yml、nginx.conf、两个 Dockerfile、backup.sh
docs/                   docs/README.md 为索引：重构方案/口径/架构/数据库/面相/基准/评测/题库/技能/安全
```

依赖方向硬约束：`api → domains → repositories/models → core`；`domains/bazi` 不 import `llm`/`billing`；`owner_user_id` 过滤只在 `repositories/` 做。以上由 `tests/test_architecture.py` 守卫（含纯计算域禁触数据库/模型、前端 api 不反向依赖 UI），具体规则与例外见 [docs/架构与验收.md](docs/架构与验收.md)。

## 3. 本机跑起来

### 3.1 前置

- Python 3.11（本项目实测 3.11.17）
- Node ≥ 20.19（实测 v25）
- MySQL 8（本项目开发实例是 Docker 容器 `xuanshu-mysql`，对外 `127.0.0.1:3307`；
  系统里 3306 上的 MySQL8 服务是另一个实例，本项目不连它。见 [docs/数据库.md](docs/数据库.md)）

### 3.2 数据库

```sql
CREATE DATABASE xuanshu DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE xuanshu_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'xuanshu_app'@'localhost' IDENTIFIED BY '<强口令>';
GRANT ALL PRIVILEGES ON xuanshu.* TO 'xuanshu_app'@'localhost';
GRANT ALL PRIVILEGES ON xuanshu_test.* TO 'xuanshu_app'@'localhost';
SET GLOBAL ngram_token_size = 2;
```

> `ngram_token_size` 必须为 2，否则中文全文检索命中率会崩。

### 3.3 后端

```bash
cd backend
cp .env.example .env          # 改 DATABASE_URL / SECRET_KEY，按需填 LLM_*
pip install -e ".[dev]"
alembic upgrade head
python -m app.domains.knowledge.ingest --approve   # 灌入 bazi 第一批片段（开发用一次性审核）
# 其余三术数各灌一次（相对路径以仓库根为基准）：
python -m app.domains.knowledge.ingest --domain ziwei  --dir docs/知识源/ziwei  --approve
python -m app.domains.knowledge.ingest --domain liuyao --dir docs/知识源/liuyao --approve
python -m app.domains.knowledge.ingest --domain qimen  --dir docs/知识源/qimen  --approve
uvicorn app.main:app --reload --port 8000
```

> 服务只读 `backend/.env`；`.env.example` 只是模板，不参与加载（历史上曾被模板里的占位值覆盖真实配置）。

- 健康检查：`GET http://127.0.0.1:8000/healthz`
- 接口文档：`http://127.0.0.1:8000/docs`
- Windows 控制台打印中文需 `set PYTHONIOENCODING=utf-8`（PowerShell：`$env:PYTHONIOENCODING='utf-8'`）

### 3.4 前端

```bash
cd frontend
cp .env.example .env
npm install
npm run dev        # http://localhost:5173，/api 代理到 127.0.0.1:8000
```

生产构建：`npm run build`（内含 `vue-tsc --noEmit`，要求零错误）。

盘面渲染冒烟（三个专属盘面用真实 `chart_facts` 做 SSR 渲染，验「拿到真实数据不崩、关键字段确实出现」）：

```bash
cd backend && PYTHONPATH=. python -m scripts.dump_board_facts   # 导出样本到 backend/var/
cd frontend && npm run check:boards                              # 渲染并校验
```

### 3.5 一条命令验证前后端契约

```bash
cd backend
python -m scripts.smoke_e2e            # 经 vite 代理跑完整链路
SMOKE_BASE=http://127.0.0.1:8000/api/v1 python -m scripts.smoke_e2e   # 直连后端
```

脚本依次走：健康检查 → 套餐 → 注册 → **四术数各排一次盘** → 四术数各存一次盘（服务端重算，客户端盘面一律不采信）→ 无额度时详版被 402 拦截 → 下单 + Mock 回调 → 四术数各生成简版报告并逐次核对账本（完成态扣 1、降级原额退回、有付费额度时不消耗免费次数）→ 幂等重放 → 详版成功 → 分享 → 导出 → 笔记 → 知识检索。任一术数的入参字段名或响应结构改坏，这里会先红。

## 4. 测试

```bash
cd backend
pytest -q                                         # 全量回归
pytest tests/test_bazi.py -q                      # 基准命例
pytest tests/test_billing_idempotency.py -q       # 并发与幂等
python -m scripts.crosscheck --samples 2000       # 与第二来源交叉核验
```

前端：

```bash
cd frontend
npm run build                                     # vue-tsc --noEmit + vite build
```

阈值与基准说明见 [docs/测试基准说明.md](docs/测试基准说明.md)，口径细节见 [docs/口径说明.md](docs/口径说明.md)，架构边界与验收分层见 [docs/架构与验收.md](docs/架构与验收.md)，文档总索引见 [docs/README.md](docs/README.md)。

## 5. 交付部署（Docker Compose）

```bash
cd infra
cp .env.example .env      # 必须改：MYSQL_ROOT_PASSWORD / MYSQL_APP_PASSWORD / SECRET_KEY
docker compose up -d --build
# 打开 http://localhost:8080
```

- 只有 nginx 对外暴露端口；后端与 MySQL 在内部网络
- 后端容器启动时自动 `alembic upgrade head`
- **首次启动后灌入知识库**（镜像内已带 `docs/知识源`）：

```bash
docker compose exec backend python -m app.domains.knowledge.ingest --approve
```

- 备份：`sh infra/backup.sh`（默认保留最近 7 份）
- 生产环境启动会自检：弱 `SECRET_KEY`、`LLM_MODE=mock`、默认 `MOCK_PAYMENT_SECRET` 会直接失败，不会静默上线

## 6. 接真实模型

只改环境变量，不动代码：

```env
LLM_MODE=openai_compatible
LLM_BASE_URL=https://<你的端点>/v1
LLM_API_KEY=<密钥>
LLM_MODEL=<模型名>
# 可选
LLM_JSON_MODE=json_object       # 模型不收 response_format 时改 prompt_only
LLM_TEMPERATURE=0.2
LLM_DAILY_TOTAL_BUDGET=500      # 当日调用次数熔断，0 表示不限
LLM_MODEL_DISCLOSURE=           # 页脚公示（模型名称 + 备案号），留空不展示
LLM_PRICE_INPUT_PER_1K=0        # 计价（元/千 token），两项为 0 则不估算成本
LLM_PRICE_OUTPUT_PER_1K=0
```

三步验证：

```bash
cd backend
python -m scripts.llm_selftest              # 连通性 + JSON 合法性 + 延迟/token
python -m scripts.eval_reports --cases 10   # 跑基准命例，写入 docs/模型评测.md（第一部分）
pytest tests/test_llm_provider.py -q        # 401/429/5xx/超时/围栏 等失败模式
```

关键约定：

- **不会静默降级成 Mock**：`LLM_MODE=openai_compatible` 但 key 为空/仍是占位值时，报告直接标为 `degraded`，页面徽章写明「未配置可用的大模型」，预扣额度全额退回。
- 每次真实调用（成功或失败）都落 `llm_calls` 表，只记 provider/model/耗时/token/成本/错误码，**不记提示词正文，也不记用户原始问题**。
- 当日调用条数达到 `LLM_DAILY_TOTAL_BUDGET` 时熔断：不发请求、不扣额度、报告标为降级并写明「今日模型调用预算已用尽」。
- 任一日志与响应都不得包含 `LLM_API_KEY`，`tests/test_llm_provider.py` 对此有断言。

### 6.1 密钥不要以明文留在 `.env`

`LLM_API_KEY` 与 `SMTP_PASSWORD` 必须能被程序还原，不能哈希，因此改为**可逆加密存储**：

```bash
cd backend
python -m scripts.encrypt_secrets --check   # 先看哪些还是明文
python -m scripts.encrypt_secrets           # 加密并把明文改成 enc:v1:...（自动备份 .env.bak）
```

- 密文用 Fernet（AES-128-CBC + HMAC-SHA256），主密钥取自 `SECRETS_MASTER_KEY`（≥32 字符）；
- 未配主密钥时回退到由 `SECRET_KEY` 经 HKDF 派生（可用，但轮换 `SECRET_KEY` 会导致旧密文解不开）；
- 生产环境启动自检会拦住「`SECRETS_MASTER_KEY` 缺失 / 密钥仍是明文」；
- 解不开时直接报错，不会静默用空 key 去请求上游。

## 7. 账号安全与找回密码

- **密码存储**：Argon2id（`time_cost=3, memory_cost=64MiB, parallelism=2`），每次带随机盐；登录时若参数已升级会自动 rehash。库里不存在明文，也不存在 MD5——`md5/sha` 属快速哈希，碰撞/字典攻击成本远低于 Argon2id（详见 `docs/查漏补缺与安全加固.md` 第 D1 节）。
- **JWT**：HS256 白名单，强制校验 `iss=xuanshu` / `aud=xuanshu-api`；access 15 分钟；refresh 7 天且**服务端轮换**——每枚 refresh 落一行 `refresh_tokens`，用过即废，重放同一 `jti` 视为被盗并作废整条登录链。
- **登出与改密**：`users.token_version` 前进一位 + 账本全作废，所有设备立即下线；`DELETE /auth/sessions` 等价于「登出所有设备」。
- **暴力破解**：IP 限流之外还按**账号**计数，连续 5 次失败锁定 15 分钟，之后按轮次翻倍（上限 24 小时）。
- **忘记密码**：`POST /auth/password/forgot` → 一次性令牌（库里只存 sha256，TTL 30 分钟，同账号只保留最近 3 枚）→ `POST /auth/password/reset`。接口对「邮箱是否存在」返回**完全一致**的响应，防账号枚举。

本地联调时 `MAIL_MODE=console`，重置邮件写到 `backend/var/mail_outbox.log`（每行一个 JSON），不会真的发信；开发环境接口还会返回 `debug_reset_url` 方便点开。生产必须 `MAIL_MODE=smtp` 并配齐 `SMTP_*`。

> 本地反复跑 `smoke_e2e` 时，可用 `RATELIMIT_ENABLED=false` 临时关掉限流（否则每 IP 5 次/小时的注册限流会把脚本自己挡住）；**生产必须保持 `true`，单测也会强制开启**。

## 8. 支付配置

`GET /billing/config` 公开当前支付模式（`mock`/`live`）、币种、可用通道与回调验签方式，**不返回任何密钥**：

| 通道 | 当前状态 | 接入时要改的地方 |
| --- | --- | --- |
| `mock` | 可用（仅非生产环境） | 无需改；已走完整 HMAC 验签 + 金额校验 + 事件去重 |
| `wechat` | 未接入 | `billing/orders.py` 建单 + `billing/webhooks.py` 验签 + `.env` 渠道密钥 |
| `alipay` | 未接入 | 同上 |

定价页会按 `/billing/config` 渲染通道选择：不可用的通道置灰并标注「未接入」，下单前有确认弹窗（金额/额度/通道/是否真扣款）。

## 9. 合规与红线

- 内容定位为传统文化研习，**不构成医疗、法律、投资、婚恋等专业建议**，不用于疾病诊断、博彩、算命收费。
- AI 生成内容在页面顶部横幅、报告区块与导出文本中均有标识。
- 知识源逐条登记 `license_status`，只用公版原文或自撰摘要；不抓取竞品内容与付费课程。
- 用户数据最小化收集：不上传邮箱、昵称、笔记正文、订单数据给模型；支持一键导出与删除，注销后 30 天物理清理。
- 仓库内不得出现真实密钥；`.env` 已在 `.gitignore` 中。

## 10. 已知限制

| 限制 | 处理方式 |
| --- | --- |
| 支付为 Mock 通道 | 定价页与 `/billing/config` 都明确标注「内测演示」，回调走真实 HMAC 校验链路 |
| 无城市经纬度表 | 真太阳时只接受直接填经度 |
| 日历输入范围 | 四柱/六爻/奇门只收公历时间；紫微可选农历并回显是否闰月 |
| 容器内节气使用自研 Meeus | 结果回显 `jieqi.prev.source`，本机若装 `lunar-python` 则优先使用并同样回显 |
| 关系规则不含吉凶判断 | 这是设计约束，不是缺失：结论交给用户与知识库原文 |
| 限流与登录锁定是进程内计数 | 单机够用；多 worker / 多机部署前必须换 Redis 或落库 |
| access token 存在 `sessionStorage` | 已是短 TTL + 每标签页隔离；残余 XSS 风险已记录，未做 BFF |
| 真实模型单份报告约 20–40 秒 | 模型侧耗时（brief 约 2–4k 输出 token）；`eval_reports` 会记录 P50/P95 |
| 追问不重新检索知识 | 只能引用原报告已引用的片段；这是为了前后口径一致，新疑点请重新生成报告 |
| 紫微大限/流年四化需手动填年龄与年份 | 未填时不出该层，也**不推断**年龄；填了才按大限宫干/流年干各推一组 |
| 同一幂等键的首次写入存在极小并发窗口 | 唯一约束保证不会重复扣费；极端并发下客户端可能收到一次 500，重试即读到同一行账本 |
| 大六壬只实现贼克法三传 | 复杂课体三传留空并在 `san_chuan_status.reason` 写明原因 |
| 太乙只实现九星观测 | 七十二局/主客算/大小将未实现，口径字段显式声明 |
| 占星只有日月 | `pyswisseph` 需 MSVC 编译装不上；未实现项通过 `unavailable` 显式列出 |
| 性格问卷 40 题（非 90+） | 题库需逐题审校，精简版信度更低，页面标注「仅供参考」 |
| 新域知识源目录未补齐 | 报告只给盘面事实，`traditional_interpretations` 为空数组 |
| 视觉模型未配置 | `/vision/*` 返回 503 `VISION_NOT_CONFIGURED`，不回落文本模型 |
| 图片留存期默认 30 天 | 到期由 `purge_expired_media` 删除；需定时任务调用 |

## 11. 报告追问

前端在报告下方内置对话框，后端只有两个接口：

- `POST /api/v1/reports/{report_id}/followups`，body `{"question": "..."}`（2–500 字），返回一轮问答；
- `GET  /api/v1/reports/{report_id}/followups`，按 `seq` 升序返回历史。

约束（实现见 `app/domains/reporting/followup.py`）：

| 项 | 规则 |
|---|---|
| 材料范围 | 原报告正文 + 原盘面事实 + 原报告 `citations_json` 里的片段，不重新检索 |
| 引用校验 | `citations ⊆ 原报告 chunk_id`，越界直接判死并重试一次 |
| 事实校验 | 复用 `DOMAIN_FACT_CHECKS`（干支/星曜/卦名/九宫门星神） |
| 轮次 | 同一报告 ≤ 20 轮，超出返回 400 `FOLLOWUP_LIMIT` |
| 额度 | **不扣额度**；但受每小时 30 次限流与 `LLM_DAILY_TOTAL_BUDGET` 约束 |
| 失败处理 | 两次都不合格 → `status=degraded`，只复述原报告已核验的事实 |

## 12. 题库评测与经验蒸馏

目的：让模型「**先查知识库作答 → 错了看为什么错 → 总结成技能卡 → 再做一遍**」这个循环可重复，而不是靠改提示词碰运气。产物是**技能卡**，不是模型权重。

已接入 **MingLi-Bench**（160 题 / 32 个命例，MIT）：数据放 `backend/data/bench/MingLi-Bench/`（已 gitignore），完整流程与已知偏差见 [docs/题库与训练数据.md](docs/题库与训练数据.md)。

```bash
cd backend
python -m scripts.prepare_bench          # 归一化 + 按命例切分（防同一张盘同时进 train/test）
python -m scripts.bench_eval --dataset mingli_bench \
    --file data/bench/MingLi-Bench/test.jsonl --limit 39 \
    --model minimax-m3.1-flash --tag mingli-test-r1
python -m scripts.bench_stats --min-wrong 1
python -m scripts.distill_skills --min-samples 2 --dry-run
```

评测时每题**先用本仓库引擎算盘**（四柱/十神/大运/流年），再检索已审核知识片段，最后才让模型选答案；排盘失败单独计数，不混进「答错」。

### 12.1 每道题错了几次：`bench_stats`

评测默认把每次作答**追加**到 `data/bench/attempts.jsonl`，`bench_stats` 把它压成可读复盘：

```bash
python -m scripts.bench_stats                        # → docs/题库复盘.md
python -m scripts.bench_stats --source mingli_bench  # 只看某个题库
python -m scripts.bench_stats --min-wrong 2          # 只看错 2 次以上的题
```

复盘表直接回答「该怎么蒸馏」：

| 指标 | 含义 |
|---|---|
| 错/答 | 同一道题错了几次 / 一共答了几次；反复错才值得写技能卡 |
| 未作答次数 | 模型没给出可解析答案（got 为空），属于格式失败，不是知识失败 |
| 错误类型 | 按 `answer_not_parsed` / `选错` 分组，决定先修提示词还是先补知识 |
| 题库缺答案 | 评测时因缺题目/选项/答案被跳过的条数（`last_load.json` 记录） |

转正流程：人工复核 `backend/skills/_draft/*.md` → 改 `status: approved` → 合并进 `backend/skills/<domain>/SKILL.md` 或 `cards/`。
SKILL.md 会在**每次 AI 调用前**注入（全局 + 领域各一份，总预算 4000 字符），详见 [docs/技能与知识源.md](docs/技能与知识源.md)。

外部技能包（如 [taibu](https://github.com/hhszzzz/taibu)）通过 `SKILLS_EXTRA_DIRS` 只读挂载：
评测时加载它的 `interpretation/<体系>.md`，报告/追问默认不加载（外部包含吉凶断语，与本站红线冲突）。
运行时会按 `domain + 触发词` 检索 top-3 卡片，以「参考经验」注入报告与追问的 prompt，并明确写死「**不是事实来源、不得写进 citations**」；校验链仍只认 `chunk_id` 与已触发 `rule_id`，卡片写错也会被拦下。

支持的格式：`generic` / `mingli_bench` / `fate_bench` / `baziqa`。适配器只做字段归一，读不到答案就跳过并计数，不猜答案。
