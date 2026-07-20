"""语义层检索抽象（RAG 预留接口）。"""

from app.retrieval.base import (
    PassthroughRetriever,
    SemanticRetriever,
    ToolError,
    current_question,
    get_retriever,
)

__all__ = [
    "PassthroughRetriever",
    "SemanticRetriever",
    "ToolError",
    "current_question",
    "get_retriever",
]
