"""RAG service for literature retrieval."""

import hashlib

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.cache.redis_client import redis_client
from src.academic.database.models import PaperChunk


class RAGService:
    """Service for RAG-based literature retrieval.

    Features:
    - Vector similarity search using pgvector
    - Redis caching for query results
    - Workspace-scoped retrieval
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_model: Embeddings | None = None,
    ):
        """Initialize RAG service.

        Args:
            db: Database session
            embedding_model: Embedding model (defaults to OpenAI ada-002)
        """
        self.db = db
        self.embedding_model = embedding_model or OpenAIEmbeddings(
            model="text-embedding-ada-002"
        )
        self.redis = redis_client

    def _hash_query(self, query: str) -> str:
        """Create hash for query caching."""
        return hashlib.md5(query.encode()).hexdigest()

    async def search(
        self,
        workspace_id: str,
        query: str,
        top_k: int = 10,
        use_cache: bool = True,
    ) -> list[dict]:
        """Search for relevant paper chunks.

        Args:
            workspace_id: Workspace ID
            query: Search query
            top_k: Number of results
            use_cache: Use Redis cache

        Returns:
            List of relevant chunks with metadata
        """
        query_hash = self._hash_query(query)

        # Check cache first
        if use_cache:
            cached = await self.redis.get_rag_cache(workspace_id, query_hash)
            if cached:
                return cached[:top_k]

        # Generate embedding
        embedding = await self.embedding_model.aembed_query(query)

        # Vector similarity search
        results = await self._vector_search(workspace_id, embedding, top_k)

        # Cache results
        if use_cache and results:
            await self.redis.set_rag_cache(workspace_id, query_hash, results)

        return results

    async def _vector_search(
        self,
        workspace_id: str,
        embedding: list[float],
        top_k: int,
    ) -> list[dict]:
        """Perform vector similarity search using pgvector.

        Args:
            workspace_id: Workspace ID
            embedding: Query embedding
            top_k: Number of results

        Returns:
            List of relevant chunks
        """
        # Use raw SQL for pgvector operations
        query = text("""
            SELECT
                pc.id,
                pc.content,
                pc.metadata,
                pc.paper_id,
                p.title as paper_title,
                p.authors,
                p.year,
                p.venue,
                1 - (pc.embedding <=> :embedding::vector) as similarity
            FROM paper_chunks pc
            JOIN papers p ON pc.paper_id = p.id
            WHERE pc.workspace_id = :workspace_id
            ORDER BY pc.embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(
            query,
            {
                "workspace_id": workspace_id,
                "embedding": embedding,
                "top_k": top_k,
            }
        )
        rows = result.fetchall()

        return [
            {
                "id": row.id,
                "content": row.content,
                "metadata": row.metadata,
                "paper_id": row.paper_id,
                "paper_title": row.paper_title,
                "authors": row.authors,
                "year": row.year,
                "venue": row.venue,
                "score": float(row.similarity),
            }
            for row in rows
        ]

    async def index_chunks(
        self,
        paper_id: str,
        workspace_id: str,
        chunks: list[str],
        metadata: dict | None = None,
    ) -> list[PaperChunk]:
        """Index paper chunks with embeddings.

        Args:
            paper_id: Paper ID
            workspace_id: Workspace ID
            chunks: List of text chunks
            metadata: Optional metadata

        Returns:
            List of created PaperChunk objects
        """
        # Generate embeddings in batch
        embeddings = await self.embedding_model.aembed_documents(chunks)

        created_chunks = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            paper_chunk = PaperChunk(
                paper_id=paper_id,
                workspace_id=workspace_id,
                chunk_index=i,
                content=chunk,
                embedding=embedding,
                metadata=metadata or {},
            )
            self.db.add(paper_chunk)
            created_chunks.append(paper_chunk)

        await self.db.commit()
        return created_chunks

    async def delete_chunks(self, paper_id: str, workspace_id: str) -> int:
        """Delete all chunks for a paper in a workspace.

        Args:
            paper_id: Paper ID
            workspace_id: Workspace ID

        Returns:
            Number of deleted chunks
        """
        result = await self.db.execute(
            text("""
                DELETE FROM paper_chunks
                WHERE paper_id = :paper_id AND workspace_id = :workspace_id
            """),
            {"paper_id": paper_id, "workspace_id": workspace_id}
        )
        await self.db.commit()
        return result.rowcount
