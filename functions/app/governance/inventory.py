"""Model inventory shared by integrations and operator release checks."""
CHAT_MODEL = "openai/gpt-oss-20b"
STT_MODEL = "whisper-large-v3"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

MODEL_INVENTORY = {
    "answer": CHAT_MODEL,
    "summary": CHAT_MODEL,
    "transcription": STT_MODEL,
    "embedding": EMBEDDING_MODEL,
}
