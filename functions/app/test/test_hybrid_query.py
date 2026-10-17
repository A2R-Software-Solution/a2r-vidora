import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.repository.transcript_chunk_repository import TranscriptChunkRepository


class HybridKeywordQueryTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self):
        db = MagicMock()
        empty = MagicMock()
        empty.all.return_value = []
        db.execute = AsyncMock(return_value=empty)
        repo = TranscriptChunkRepository(db)
        result = await repo.hybrid_search(uuid.uuid4(), [0.0] * 384, "who wrote the book", top_k=5)
        return result, str(db.execute.await_args.args[0])

    async def test_lexical_branch_uses_or_semantics_with_ordered_limit(self):
        result, sql = await self._run()
        self.assertEqual(result, [])
        self.assertIn("' & ', ' | '", sql)
        self.assertIn("lexical_query.tsq", sql)
        keyword = sql[sql.index("keyword as"):sql.index("fused as")]
        self.assertLess(keyword.index("order by ts_rank"), keyword.index("limit :candidate_pool"))
        self.assertNotIn("search_vector @@ plainto_tsquery", sql)


if __name__ == "__main__":
    unittest.main()
