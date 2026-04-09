"""注册 ORM 模型，供 Base.metadata.create_all 使用。"""

from app.models.answer_log import AnswerLog
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.eval_task import EvalTask
from app.models.feedback import Feedback
from app.models.graph_entity import GraphEntity
from app.models.message import Message
from app.models.rerank_log import RerankLog
from app.models.retrieval_log import RetrievalLog
from app.models.role import Role, UserRole
from app.models.session import ChatSession
from app.models.user import User

__all__ = [
    "AnswerLog",
    "ChatSession",
    "Chunk",
    "Document",
    "EvalTask",
    "Feedback",
    "GraphEntity",
    "Message",
    "RerankLog",
    "RetrievalLog",
    "Role",
    "User",
    "UserRole",
]
