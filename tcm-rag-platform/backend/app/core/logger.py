"""
统一 JSON 日志 — 所有模块通过 get_logger() 获取 logger。
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# 全局 trace_id 上下文变量，由 TraceIDMiddleware 设置
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")


class JSONFormatter(logging.Formatter):
    """将日志记录序列化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": trace_id_ctx.get("-"),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """初始化根 logger，设置 JSON 格式输出到 stdout。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # 避免重复添加 handler
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """获取带有指定名称的 logger。"""
    return logging.getLogger(name)
