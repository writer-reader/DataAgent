"""工具层单元测试。

运行: pytest tests/ -v
注意: test_execute_sql 需要先初始化数据库
    (python scripts/init_database.py && python scripts/seed_database.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.config import settings
from app.retrieval.base import PassthroughRetriever, ToolError
from app.tools.execute_sql import _validate_select, execute_sql
from app.tools.finalize import finalize_report
from app.tools.registry import execute_tool, result_to_str


# ---------- PassthroughRetriever（探索工具） ----------

class TestPassthroughRetriever:
    def setup_method(self):
        self.r = PassthroughRetriever()

    def test_list_files_contains_catalog(self):
        files = self.r.list_files()
        assert "catalog.yml" in files
        assert "entities/Company.yml" in files

    def test_read_file_full_content(self):
        content = self.r.read_file("entities/Company.yml")
        assert "main.companies" in content   # 表名必须完整可见
        assert "joins:" in content           # join 定义必须完整可见

    def test_read_missing_file_lists_alternatives(self):
        with pytest.raises(ToolError, match="可用文件"):
            self.r.read_file("entities/Nope.yml")

    def test_path_traversal_blocked(self):
        """安全: ../.. 越界访问必须被拒绝。"""
        with pytest.raises(ToolError, match="越界"):
            self.r.read_file("../../etc/passwd")

    def test_search_returns_file_line_format(self):
        hits = self.r.search("monthly_value")
        assert "Accounts.yml" in hits
        assert ":" in hits  # 文件:行号:内容 格式

    def test_search_invalid_regex_falls_back_to_literal(self):
        """非法正则应降级为字面量搜索而非报错。"""
        result = self.r.search("salary (USD")  # 未闭合括号
        assert isinstance(result, str)


# ---------- SQL 校验与执行 ----------

class TestValidateSelect:
    def test_select_allowed(self):
        assert _validate_select("SELECT 1") is None

    def test_cte_allowed(self):
        assert _validate_select("WITH t AS (SELECT 1 AS x) SELECT x FROM t") is None

    @pytest.mark.parametrize("sql", [
        "INSERT INTO companies (name, industry) VALUES ('x', 'y')",
        "UPDATE companies SET name='x'",
        "DELETE FROM companies",
        "DROP TABLE companies",
        "PRAGMA table_info(companies)",
    ])
    def test_writes_rejected(self, sql):
        assert _validate_select(sql) is not None

    def test_multiple_statements_rejected(self):
        assert _validate_select("SELECT 1; SELECT 2") is not None


@pytest.mark.skipif(not settings.db_file.exists(), reason="数据库未初始化")
class TestExecuteSQL:
    def test_basic_query(self):
        result = execute_sql("SELECT COUNT(*) AS n FROM companies")
        assert result["ok"] is True
        assert result["rows"][0]["n"] == 50   # seed 固定 50 家公司

    def test_bad_column_returns_error_dict(self):
        result = execute_sql("SELECT nonexistent_col FROM companies")
        assert result["ok"] is False
        assert "error" in result

    def test_insert_rejected(self):
        result = execute_sql("INSERT INTO companies (name, industry) VALUES ('a', 'b')")
        assert result["ok"] is False


# ---------- FinalizeReport ----------

class TestFinalize:
    def test_valid_report(self):
        r = finalize_report(sql="SELECT 1", csv_results="n\n1", narrative="答案是 1。")
        assert r["ok"] is True

    def test_empty_narrative_rejected(self):
        r = finalize_report(sql="SELECT 1", csv_results="", narrative="")
        assert r["ok"] is False


# ---------- 注册表分发 ----------

class TestRegistry:
    def test_dispatch_list_files(self):
        result = execute_tool("list_files", "{}")
        assert "catalog.yml" in result

    def test_unknown_tool(self):
        result = execute_tool("Nope", "{}")
        assert result["ok"] is False

    def test_bad_json_arguments(self):
        result = execute_tool("read_file", "{not json")
        assert result["ok"] is False

    def test_hallucinated_kwarg(self):
        """模型幻觉出不存在的参数时返回错误而非崩溃。"""
        result = execute_tool("list_files", '{"bogus": 1}')
        assert result["ok"] is False

    def test_result_to_str(self):
        assert result_to_str("plain") == "plain"
        assert '"ok"' in result_to_str({"ok": True})
