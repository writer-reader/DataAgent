"""全局配置。

用 pydantic-settings 从 .env / 环境变量加载，带类型校验。
所有模块通过 `from app.config import settings` 获取配置，
避免散落的 os.getenv 调用。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（app/ 的上一级），路径类配置都相对它解析，
# 这样无论从哪个目录启动（uvicorn / pytest / CLI）都能找到文件
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """应用配置。字段名与 .env 中的变量一一对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里多余的变量不报错
    )

    # --- OpenAI 兼容接口 ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"

    # --- Agent 行为 ---
    max_steps: int = 100      # 最大工具调用轮数（对应原项目 stepCountIs(100)）
    sql_row_limit: int = 1001  # 单次查询最大返回行数（原项目 LIMIT 1001）

    # --- 路径（相对项目根） ---
    db_path: str = "data/dataagent.db"
    semantic_dir: str = "semantic"

    # --- 检索器实现: passthrough | vector（P5 RAG） ---
    retriever: str = "passthrough"

    @property
    def db_file(self) -> Path:
        """数据库文件的绝对路径。"""
        return PROJECT_ROOT / self.db_path

    @property
    def semantic_root(self) -> Path:
        """语义层目录的绝对路径。"""
        return PROJECT_ROOT / self.semantic_dir


# 模块级单例：import 时加载一次
settings = Settings()
