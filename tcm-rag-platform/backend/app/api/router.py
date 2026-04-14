"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import admin, auth, case_profiles, chats, documents, evaluation, feedback, knowledge_graph, rag, users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(case_profiles.router, prefix="/case-profiles", tags=["角色档案"])
api_router.include_router(chats.router, prefix="/chats", tags=["对话"])
api_router.include_router(rag.router, prefix="/rag", tags=["RAG"])
api_router.include_router(documents.router, prefix="/documents", tags=["文档管理"])
api_router.include_router(admin.router, prefix="/admin", tags=["管理后台"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["反馈"])
api_router.include_router(evaluation.router, prefix="/evaluation", tags=["评测"])
api_router.include_router(knowledge_graph.router, prefix="/graph", tags=["知识图谱"])
