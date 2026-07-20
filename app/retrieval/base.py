"""语义层检索抽象 —— RAG 预留接口。

设计意图（重要）：
    探索工具（app/tools/explore.py）不直接读文件系统，而是通过本模块的
    SemanticRetriever 协议中转。初版只有 PassthroughRetriever（直通文件系统，
    等价于原项目沙箱里的 cat/grep/ls）。

    当语义层膨胀到几百个实体、无法全量浏览时，新增一个 VectorRetriever
    （向量召回 top-k 相关实体做"预筛选"），工具层和 Agent 循环零改动，
    只需把 .env 的 RETRIEVER 改为 vector。

关键原则：RAG 只控制"文件可见性"（list_files/search 返回哪些候选），
    不截断"文件内容"（read_file 永远返回完整 YAML）。
    写 SQL 需要完整的字段列表和 join 定义，残缺的 schema 会让模型猜字段。
    即使召回漏了实体，Agent 仍可通过 search 关键词兜底找回——保持探索式架构的鲁棒性。
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from pathlib import Path
from typing import Protocol

from app.config import settings

# 当前用户问题（request 级上下文）。
# Agent 循环在每轮开始时 set，VectorRetriever 可选读取用于向量召回；
# PassthroughRetriever 忽略它。工具签名对模型保持不变。
current_question: ContextVar[str | None] = ContextVar("current_question", default=None)


class ToolError(Exception):
    """工具执行错误。message 会原样返回给模型（模型据此自我修正）。"""


class SemanticRetriever(Protocol):
    """语义层检索协议。探索工具只依赖此接口。"""

    def list_files(self) -> str:
        """列出（可见的）语义层文件。RAG 版可按 current_question 预筛选。"""
        ...

    def read_file(self, path: str) -> str:
        """读取单个文件的【完整】内容。任何实现都不得截断。"""
        ...

    def search(self, pattern: str) -> str:
        """跨文件搜索。初版=grep；RAG 版=向量召回+grep 并集。"""
        ...


class PassthroughRetriever:
    """初版实现：直通文件系统。

    等价于原项目 Vercel Sandbox 中的三个 shell 命令：
        list_files ≈ ls -R    read_file ≈ cat    search ≈ grep -rin
    """

    def __init__(self, root: Path | None = None):
        # resolve() 得到绝对规范路径，是路径穿越校验的基准
        self.root = (root or settings.semantic_root).resolve()

    # ---- 内部工具 ----

    def _safe(self, rel: str) -> Path:
        """把相对路径解析到语义层根目录下，拒绝任何越界访问。

        防御 "../../etc/passwd" 或绝对路径这类穿越尝试：
        resolve() 展开所有 .. 和符号链接后，结果必须仍在 root 内。
        """
        p = (self.root / rel).resolve()
        if not p.is_relative_to(self.root):
            raise ToolError(f"路径越界，只能访问语义层目录内的文件: {rel}")
        return p

    def _all_files(self) -> list[Path]:
        """语义层下所有 YAML 文件（排序保证输出稳定）。"""
        return sorted(self.root.rglob("*.yml")) + sorted(self.root.rglob("*.yaml"))

    # ---- SemanticRetriever 实现 ----

    def list_files(self) -> str:
        files = self._all_files()
        if not files:
            raise ToolError(f"语义层目录为空: {self.root}")
        # 输出相对路径，模型直接把它传给 read_file 即可
        return "\n".join(str(f.relative_to(self.root)).replace("\\", "/") for f in files)

    def read_file(self, path: str) -> str:
        p = self._safe(path)
        if not p.is_file():
            # 给出可用文件列表，帮模型一次性纠正（省一轮 list_files 调用）
            raise ToolError(f"文件不存在: {path}\n可用文件:\n{self.list_files()}")
        return p.read_text(encoding="utf-8")

    def search(self, pattern: str) -> str:
        """跨文件正则搜索，输出格式对齐 grep -rin: '文件:行号:内容'。"""
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # 非法正则降级为字面量搜索，而不是报错——模型经常传含特殊字符的词
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        hits: list[str] = []
        for f in self._all_files():
            rel = str(f.relative_to(self.root)).replace("\\", "/")
            for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{rel}:{lineno}:{line.strip()}")
        if not hits:
            return f"(无匹配: {pattern})"
        # 上限保护：单次搜索最多返回 200 行，避免撑爆上下文
        if len(hits) > 200:
            hits = hits[:200] + [f"... 共 {len(hits)} 处匹配，已截断到 200 行"]
        return "\n".join(hits)


def get_retriever() -> SemanticRetriever:
    """按配置返回检索器实例（工厂函数，RAG 的切换开关就在这里）。"""
    if settings.retriever == "passthrough":
        return PassthroughRetriever()
    # P5: elif settings.retriever == "vector": return VectorRetriever()
    raise ValueError(f"未知的检索器实现: {settings.retriever}")
