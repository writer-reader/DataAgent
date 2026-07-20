"""FinalizeReport 工具 —— 结构化收尾。

对应原项目的 FinalizeReport（Zod schema）。execute 逻辑就是"原样返回"（identity），
它存在的意义有两个：
    1. 强制模型以固定结构（sql/csv_results/narrative）交付最终答案
    2. 作为 Agent 循环的终止信号（对应原项目的 stopWhen 逻辑）
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError


class FinalReport(BaseModel):
    """最终报告结构，与原项目 FinalizeReportSchema 字段一致。"""

    sql: str = Field(description="最终执行（或尝试）的 SQL")
    csv_results: str = Field(description="结果 CSV 文本（表头+数据行），无结果则为空串")
    narrative: str = Field(min_length=1, description="叙述性回答")


def finalize_report(sql: str = "", csv_results: str = "", narrative: str = "") -> dict:
    """校验并返回报告。校验失败返回 {ok: False, error}，模型会补齐字段重试。"""
    try:
        report = FinalReport(sql=sql, csv_results=csv_results, narrative=narrative)
        return {"ok": True, **report.model_dump()}
    except ValidationError as e:
        return {"ok": False, "error": f"报告字段校验失败: {e}"}


FINALIZE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "FinalizeReport",
        "description": (
            "Finalize the report with SQL, CSV results, and narrative. "
            "Call this exactly once when you have the answer (or must report failure). "
            "This ends the analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The final SQL query that was executed (or attempted)",
                },
                "csv_results": {
                    "type": "string",
                    "description": "Results as CSV text (header row + data rows), or empty string",
                },
                "narrative": {
                    "type": "string",
                    "description": "Clear answer with data, assumptions and caveats (3-6 sentences)",
                },
            },
            "required": ["sql", "csv_results", "narrative"],
        },
    },
}
