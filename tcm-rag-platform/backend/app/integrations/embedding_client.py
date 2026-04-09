"""DashScope Embedding Client (text-embedding-v3)"""
import dashscope
from dashscope import TextEmbedding
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingClient:
    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIM

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化"""
        # DashScope text-embedding-v3 batch限制10条
        BATCH_SIZE = 10
        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i+BATCH_SIZE]
            response = TextEmbedding.call(
                model=self.model,
                input=batch,
                dimension=self.dimension,
            )
            if response.status_code == 200:
                embeddings = [item['embedding'] for item in response.output['embeddings']]
                all_embeddings.extend(embeddings)
            else:
                raise Exception(f"Embedding API error: {response.code} - {response.message}")
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        """单条查询向量化"""
        result = await self.embed_texts([text])
        return result[0]


embedding_client = EmbeddingClient()
