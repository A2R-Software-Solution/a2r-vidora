"""Map independently transcribed VAD chunks back onto the original video clock."""
import math

from app.pipeline.audio_chunker import AudioChunk, SAMPLE_RATE


def assemble_words(chunks: tuple[AudioChunk, ...], results: dict[str, list[dict]]) -> list[dict]:
    ordered = sorted(chunks, key=lambda chunk: chunk.sequence_number)
    if len({chunk.id for chunk in ordered}) != len(ordered) or set(results) != {c.id for c in ordered}:
        raise ValueError("Transcript results must match every audio chunk exactly once")
    segments = []
    for i, chunk in enumerate(ordered):
        if chunk.sequence_number != i:
            raise ValueError("Missing audio chunk sequence")
        start = chunk.start_sample / SAMPLE_RATE
        end = chunk.end_sample / SAMPLE_RATE
        left, right = start, end
        if i and ordered[i - 1].end_sample > chunk.start_sample:
            left = (ordered[i - 1].end_sample + chunk.start_sample) / (2 * SAMPLE_RATE)
        if i + 1 < len(ordered) and chunk.end_sample > ordered[i + 1].start_sample:
            right = (chunk.end_sample + ordered[i + 1].start_sample) / (2 * SAMPLE_RATE)
        for word in results[chunk.id]:
            text = word["word"].strip()
            local_start, local_end = float(word["start"]), float(word["end"])
            if (not math.isfinite(local_start) or not math.isfinite(local_end)
                    or local_start < 0 or local_end < local_start or local_end > end - start + 0.25):
                raise ValueError("Invalid STT word timestamp")
            word_start = min(start + local_start, end)
            word_end = min(start + local_end, end)
            # Assign overlap to just one side; never dedup phrases globally,
            # because a speaker may legitimately repeat the same words.
            if text and word_end > word_start and left <= (word_start + word_end) / 2 < right:
                segments.append({"text": text, "start": max(word_start, left), "end": min(word_end, right)})
    return sorted(segments, key=lambda segment: (segment["start"], segment["end"]))
