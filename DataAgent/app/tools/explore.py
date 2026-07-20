"""语义层探索工具 —— 替代原项目的 Vercel Sandbox + bash。

原项目给模型一个真 bash 跑 cat/grep/ls；这里用三个只读函数实现等价能力：
    list_files ≈ ls -R semantic/
    read_file  ≈ cat semantic/<path>
    search     ≈ grep -rin <pattern> semantic/

所有函数经 SemanticRetriever 接口中转（不直接碰文件系统），
这就是 RAG 预筛选的注入点——见 app/retrieval/base.py 的模块注释。
"""

from __future__ import annotations

from app.retrieval import get_retriever

# 模块级单例。get_retriever() 按 .env 的 RETRIEVER 配置决定实现
_retriever = get_retriever()


def list_files() -> str:
    """列出语义层的所有文件（相对路径，可直接传给 read_file）。"""
    return _retriever.list_files()


def read_file(path: str) -> str:
    """读取一个语义层文件的完整内容。"""
    return _retriever.read_file(path)


def search(pattern: str) -> str:
    """在所有语义层文件中搜索关键词/正则，返回 '文件:行号:内容' 格式。"""
    return _retriever.search(pattern)


# ---- OpenAI function-calling 工具定义 ----
# 描述文本是给模型看的"使用说明书"，质量直接影响模型的探索效率

EXPLORE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List all semantic layer files. Start here to see what's available. "
                "Returns relative paths usable with read_file."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full content of a semantic layer file. "
                "Use on catalog.yml first to browse entities, then on "
                "entities/<Name>.yml to get table names, fields, and joins."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path, e.g. 'catalog.yml' or 'entities/Company.yml'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search all semantic layer files for a keyword or regex "
                "(case-insensitive). Returns 'file:line:content' matches. "
                "Useful to find which entity contains a field or concept."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Keyword or regular expression to search for",
                    }
                },
                "required": ["pattern"],
            },
        },
    },
]
