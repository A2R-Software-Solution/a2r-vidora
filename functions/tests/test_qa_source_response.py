import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from app.schemas.qa_logs_schema import QALogResponse


class SourceResponseTests(unittest.TestCase):
    def setUp(self):
        self.log = SimpleNamespace(id=uuid.uuid4(), video_id=uuid.uuid4(), user_id=None,
                                   question="Question", answer="Answer", created_at=datetime.now(timezone.utc))

    def test_history_without_sources_stays_unknown(self):
        self.assertIsNone(QALogResponse.model_validate(self.log).sources)

    def test_no_context_is_explicit_empty_list(self):
        self.log.sources = []
        self.assertEqual(QALogResponse.model_validate(self.log).sources, [])

    def test_actual_source_text_and_timestamps_are_serialized(self):
        self.log.sources = [{"text": "Original excerpt", "start_time": 65, "end_time": 80}]
        response = QALogResponse.model_validate(self.log).model_dump()
        self.assertEqual(response["sources"], self.log.sources)
