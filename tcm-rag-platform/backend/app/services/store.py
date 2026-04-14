"""内存态 demo 数据仓库。

当前阶段先用可运行的内存实现，把 PRD 对应的主链路打通。
后续接 MySQL / ES / 向量库时，可以保留 service 与 API 契约不变。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from app.core.security import password_hash


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class UserRecord:
    id: int
    username: str
    email: str
    password_hash: str
    role: str
    status: str = "active"
    created_at: str = field(default_factory=utcnow_iso)


@dataclass
class SessionRecord:
    session_id: str
    user_id: int
    title: str
    summary: str | None = None
    case_profile_id: int | None = None
    case_profile_name: str | None = None
    case_profile_summary: str | None = None
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)


@dataclass
class MessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    citations: list[dict[str, Any]] | None = None
    rewritten_query: str | None = None
    latency_ms: int | None = None
    created_at: str = field(default_factory=utcnow_iso)


@dataclass
class DocumentRecord:
    doc_id: str
    title: str
    source: str
    version: int
    status: str
    authority_score: float
    uploaded_by: int
    created_at: str = field(default_factory=utcnow_iso)
    published_at: str | None = None
    excerpt: str | None = None
    keywords: list[str] = field(default_factory=list)
    review_comment: str | None = None


@dataclass
class FeedbackRecord:
    id: int
    message_id: str
    user_id: int
    feedback_type: str
    content: str | None = None
    created_at: str = field(default_factory=utcnow_iso)


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.users: dict[int, UserRecord] = {}
            self.sessions: dict[str, SessionRecord] = {}
            self.messages: dict[str, MessageRecord] = {}
            self.documents: dict[str, DocumentRecord] = {}
            self.feedbacks: dict[int, FeedbackRecord] = {}
            self.session_messages: dict[str, list[str]] = {}
            self._user_id_seq = 1
            self._feedback_id_seq = 1
            self._seed()

    def _seed(self) -> None:
        admin = self.add_user(
            username="admin",
            email="admin@tcm.local",
            password="admin123",
            role="admin",
        )
        self.add_user(
            username="reviewer",
            email="reviewer@tcm.local",
            password="reviewer123",
            role="reviewer",
        )
        self.add_user(
            username="operator",
            email="operator@tcm.local",
            password="operator123",
            role="operator",
        )
        demo_user = self.add_user(
            username="demo",
            email="demo@tcm.local",
            password="demo123",
            role="user",
        )

        neijing = self.add_document(
            title="黄帝内经·素问",
            source="古籍",
            uploaded_by=admin.id,
            status="published",
            authority_score=0.98,
            published_at=utcnow_iso(),
            excerpt="阳气尽则卧，阴气尽则寤。情志失调、肝胆郁热、阴阳失和，皆可影响寐醒节律。",
            keywords=["失眠", "口苦", "肝火", "情志", "睡眠"],
        )
        self.add_document(
            title="伤寒论",
            source="古籍",
            uploaded_by=admin.id,
            status="published",
            authority_score=0.97,
            published_at=utcnow_iso(),
            excerpt="太阳病，发热汗出恶风者，桂枝汤主之。适用于营卫不和、表虚有汗等证候参考。",
            keywords=["发热", "恶风", "感冒", "汗出", "桂枝汤"],
        )
        self.add_document(
            title="本草纲目·当归",
            source="古籍",
            uploaded_by=admin.id,
            status="published",
            authority_score=0.95,
            published_at=utcnow_iso(),
            excerpt="当归，补血和血，调经止痛，润燥滑肠。多用于血虚、经行失调等知识检索场景。",
            keywords=["当归", "补血", "调经", "月经不调"],
        )
        self.add_document(
            title="脾胃论",
            source="古籍",
            uploaded_by=admin.id,
            status="published",
            authority_score=0.94,
            published_at=utcnow_iso(),
            excerpt="脾胃为后天之本，饮食劳倦最易伤脾。食少乏力、腹胀便溏，多从脾胃失和求之。",
            keywords=["脾胃虚弱", "乏力", "腹胀", "食少"],
        )
        self.add_document(
            title="温病条辨",
            source="古籍",
            uploaded_by=admin.id,
            status="pending",
            authority_score=0.92,
            excerpt="温病初起，多见发热、咽痛、口渴。辨卫气营血，是温病条辨的重要脉络。",
            keywords=["发热", "咽痛", "温病", "口渴"],
        )

        session = self.create_session(demo_user.id, title="失眠调理建议")
        self.add_message(
            session.session_id,
            role="user",
            content="最近总是失眠、口苦，还容易烦躁，想了解中医一般怎么辨证。",
            rewritten_query="失眠 口苦 烦躁 中医辨证 古籍依据",
        )
        assistant = self.add_message(
            session.session_id,
            role="assistant",
            content=(
                "症状分析：失眠伴口苦、烦躁，常见于情志不舒或肝胆郁热相关线索。\n"
                "可能相关证候/知识点：可从肝火扰心、少阳郁热、阴阳失和等方向检索。\n"
                "建议参考方向：建议继续结合舌脉、作息、饮食和病程做辨证，不宜只凭单一症状定论。\n"
                "风险提示：若长期失眠明显影响日常生活，或伴胸闷心悸等不适，应及时线下就医。\n"
                "引用来源：黄帝内经·素问"
            ),
            citations=[
                {
                    "chunk_id": f"{neijing.doc_id}-chunk-1",
                    "doc_title": neijing.title,
                    "text": neijing.excerpt or "",
                }
            ],
            latency_ms=482,
        )
        self.add_feedback(assistant.id, demo_user.id, "thumbs_up")

    def add_user(self, username: str, email: str, password: str, role: str) -> UserRecord:
        user = UserRecord(
            id=self._user_id_seq,
            username=username,
            email=email,
            password_hash=password_hash(password),
            role=role,
        )
        self.users[user.id] = user
        self._user_id_seq += 1
        return user

    def create_session(
        self,
        user_id: int,
        title: str = "新对话",
        case_profile_id: int | None = None,
        case_profile_name: str | None = None,
        case_profile_summary: str | None = None,
    ) -> SessionRecord:
        session = SessionRecord(
            session_id=str(uuid4()),
            user_id=user_id,
            title=title,
            case_profile_id=case_profile_id,
            case_profile_name=case_profile_name,
            case_profile_summary=case_profile_summary,
        )
        self.sessions[session.session_id] = session
        self.session_messages[session.session_id] = []
        return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        rewritten_query: str | None = None,
        latency_ms: int | None = None,
    ) -> MessageRecord:
        message = MessageRecord(
            id=str(uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            citations=citations,
            rewritten_query=rewritten_query,
            latency_ms=latency_ms,
        )
        self.messages[message.id] = message
        self.session_messages.setdefault(session_id, []).append(message.id)
        session = self.sessions[session_id]
        session.updated_at = utcnow_iso()
        if role == "user" and session.title == "新对话":
            session.title = content.strip().replace("\n", " ")[:16] or "新对话"
        return message

    def add_document(
        self,
        title: str,
        source: str,
        uploaded_by: int,
        status: str = "pending",
        authority_score: float = 0.75,
        version: int = 1,
        published_at: str | None = None,
        excerpt: str | None = None,
        keywords: list[str] | None = None,
    ) -> DocumentRecord:
        document = DocumentRecord(
            doc_id=str(uuid4()),
            title=title,
            source=source,
            version=version,
            status=status,
            authority_score=authority_score,
            uploaded_by=uploaded_by,
            published_at=published_at,
            excerpt=excerpt,
            keywords=keywords or [],
        )
        self.documents[document.doc_id] = document
        return document

    def add_feedback(
        self,
        message_id: str,
        user_id: int,
        feedback_type: str,
        content: str | None = None,
    ) -> FeedbackRecord:
        feedback = FeedbackRecord(
            id=self._feedback_id_seq,
            message_id=message_id,
            user_id=user_id,
            feedback_type=feedback_type,
            content=content,
        )
        self.feedbacks[feedback.id] = feedback
        self._feedback_id_seq += 1
        return feedback


store = InMemoryStore()
