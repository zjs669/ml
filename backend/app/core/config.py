"""应用配置：全部来自环境变量 / .env，不在代码中出现任何密钥。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

# 占位值识别：示例配置里写的是 replace_with_secret / replace_with_authorized_model，
# 不把这种值当成“已配置”，否则上线后会拿着假 key 去打上游并得到 401。
PLACEHOLDER_MARKERS = ("replace_with", "change-me", "your_", "example.com")


def _is_placeholder(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return True
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    # 只读 `.env`：`.env.example` 只是模板，若参与加载会用占位值覆盖真实配置
    # （历史坑：LLM_MODEL 曾被模板里的 replace_with_authorized_model 盖掉）。
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 应用
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "玄枢国学研习台"
    api_prefix: str = "/api/v1"
    secret_key: str = "dev-only-change-me-please-use-32-bytes-min"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    refresh_cookie_name: str = "xuanshu_refresh"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 数据库
    database_url: str = (
        "mysql+pymysql://xuanshu_app:XuanShuDev_2026@127.0.0.1:3307/xuanshu?charset=utf8mb4"
    )
    test_database_url: str = (
        "mysql+pymysql://xuanshu_app:XuanShuDev_2026@127.0.0.1:3307/xuanshu_test?charset=utf8mb4"
    )

    # 模型
    llm_mode: Literal["mock", "openai_compatible"] = "mock"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.example.com/v1"
    llm_api_key: str = ""
    llm_model: str = "mock-model"
    llm_timeout_seconds: int = 45
    llm_max_output_tokens: int = 3000
    llm_daily_total_budget: int = 500
    # 部分国产模型不支持 response_format=json_object，可切到纯提示词约束
    llm_json_mode: Literal["json_object", "prompt_only"] = "json_object"
    llm_temperature: float = 0.2
    # 页脚公示用：模型名称与备案号/上线编号，留空则不展示
    llm_model_disclosure: str = ""
    # 计价（元 / 千 token）；两项都为 0 时不估算成本
    llm_price_input_per_1k: float = 0.0
    llm_price_output_per_1k: float = 0.0

    # 额度与付费
    daily_free_report_limit: int = 1
    report_data_retention_days: int = 90
    mock_payment_secret: str = "mock-webhook-secret-change-me"

    # ---- 密钥静态加密 ----
    #: 加密 LLM_API_KEY / SMTP_PASSWORD 用的主密钥（≥32 字符）。
    #: 留空时退回「由 SECRET_KEY 经 HKDF 派生」，可用但轮换 SECRET_KEY 会解不开旧密文。
    secrets_master_key: str = ""

    # ---- 技能文件 ----
    #: 本仓库技能目录（backend/skills）之外的外部技能包根目录，多个用逗号或分号分隔。
    #: 典型值：D:/瞎玩/taibu/skills/taibu-divination
    skills_extra_dirs: str = ""
    #: 是否在「报告/追问」中也注入外部技能包（默认关：外部包的断语口径与本站红线不同）
    skills_external_in_product: bool = False

    # ---- 账号安全 ----
    #: 重置令牌有效期（分钟）
    password_reset_ttl_minutes: int = 30
    #: 同一用户同时保留的可用重置令牌数，超出时作废最早的
    password_reset_max_active: int = 3
    #: 同账号连续失败多少次后锁定
    login_max_failures: int = 5
    #: 锁定基础时长（分钟），第 N 次锁定按 N 倍递延
    login_lock_minutes: int = 15
    #: 重置邮件里链接的前端地址
    frontend_base_url: str = "http://localhost:5173"
    #: 限流开关。生产必须为 true；本地反复跑 smoke_e2e 时可临时关掉
    ratelimit_enabled: bool = True

    # ---- 邮件通道（忘记密码）----
    #: console = 写本地发信箱（开发默认，不投递）；smtp = 走真实邮件服务器
    mail_mode: Literal["console", "smtp"] = "console"
    mail_from: str = "no-reply@xuanshu.local"
    #: console 模式的发信箱路径，留空则用 backend/var/mail_outbox.log
    mail_outbox_path: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_ssl: bool = True

    # 算法
    bazi_algorithm_version: str = "bazi-engine-0.1.0"
    ziwei_algorithm_version: str = "ziwei-engine-0.1.0"
    liuyao_algorithm_version: str = "liuyao-engine-0.1.0"
    qimen_algorithm_version: str = "qimen-engine-0.1.0"
    relations_rule_version: str = "relations-rules-0.1.0"
    # system_v2：在 v1 基础上加「篇幅控制 + 字段级要求」（真实模型实测 v1 易超时/截断）
    prompt_version: str = "system_v2"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def llm_api_key_value(self) -> str:
        """实际使用的模型密钥：兼容 `enc:v1:` 密文与历史明文。"""
        from app.core.secrets import decrypt_value

        return decrypt_value(self.llm_api_key)

    @property
    def smtp_password_value(self) -> str:
        """实际使用的 SMTP 密码：兼容密文与历史明文。"""
        from app.core.secrets import decrypt_value

        return decrypt_value(self.smtp_password)

    @property
    def llm_configured(self) -> bool:
        """真实模型是否具备可调用条件；前端据此区分「真实模型」与「演示模型」。"""
        return self.llm_mode == "openai_compatible" and not _is_placeholder(self.llm_api_key_value)

    def estimate_cost(self, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if not input_tokens and not output_tokens:
            return None
        if self.llm_price_input_per_1k <= 0 and self.llm_price_output_per_1k <= 0:
            return None
        return round(
            (input_tokens or 0) / 1000 * self.llm_price_input_per_1k
            + (output_tokens or 0) / 1000 * self.llm_price_output_per_1k,
            6,
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def assert_safe_for_production(self) -> None:
        """生产环境自检：弱密钥 / mock 模型必须显式失败，而不是静默上线。"""
        if not self.is_production:
            return
        problems: list[str] = []
        if "dev-only" in self.secret_key or len(self.secret_key) < 32:
            problems.append("SECRET_KEY 仍是开发默认值或长度不足 32 字符")
        if self.llm_mode == "mock":
            problems.append("LLM_MODE=mock 不允许在生产环境启用")
        elif not self.llm_configured:
            problems.append("LLM_API_KEY 为空或仍是占位值，生产环境无法调用真实模型")
        if "change-me" in self.mock_payment_secret:
            problems.append("MOCK_PAYMENT_SECRET 仍是默认值")
        # 密钥必须密文存储：镜像层、备份、截图泄露时明文等于直接交出账号
        from app.core.secrets import is_encrypted, using_derived_master

        if not self.secrets_master_key:
            problems.append("SECRETS_MASTER_KEY 未配置，密钥只能由 SECRET_KEY 派生（轮换即失效）")
        elif using_derived_master():
            problems.append("SECRETS_MASTER_KEY 长度不足，无法用作主密钥")
        for name, value in (("LLM_API_KEY", self.llm_api_key), ("SMTP_PASSWORD", self.smtp_password)):
            if value and not is_encrypted(value):
                problems.append(f"{name} 仍为明文，请执行 python -m scripts.encrypt_secrets")
        if problems:
            raise RuntimeError("生产配置自检失败: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
