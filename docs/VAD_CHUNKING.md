# Product ingestion: VAD chunks and quota-aware STT

The actual `POST /videos/analyze` ingestion now runs:

```text
YouTube download + metadata
  -> normalized 16 kHz audio
  -> Silero VAD speech detection
  -> short-pause merge / capped audio chunks
  -> pack adjacent VAD clips into capped Groq WAV requests, shortening long gaps
  -> shared quota reservation + bounded parallel Groq STT (word timestamps)
  -> global timestamp mapping / overlap ownership / chronological assembly
  -> existing text chunking and MiniLM embeddings
  -> summary
  -> transcript rows + completed video status committed together
```

This is enabled in the product pipeline, not a feature-flagged preview. The same
chunking implementation also powers the optional local listening preview below.
Shared settings live in `app/core/vad_config.py`, loaded by application config.
Production requirements now include `requirements-vad.txt`; deploy with these
dependencies installed. FFmpeg must be available in the function runtime. VAD
model loading/inference is cached and locked per process and runs off the async
event loop. The HTTP response contract remains unchanged; the frontend reports
quota waits and STT request progress.

Cloud Tasks accepts the submitted job and the HTTP endpoint returns its
`PROCESSING` video record immediately. The worker performs the paid processing.
Cloud Tasks retries transient worker failures according to `TASK_MAX_ATTEMPTS`.
STT is bounded by `STT_CONCURRENCY` (default 3) and shared PostgreSQL RPM,
hourly audio, and daily audio reservations. Audio chunk IDs are namespaced by
the video ID; manifests and WAVs are temporary. Completed STT request results
are checkpointed by video, sequence, and audio hash. Quota waits over ten
seconds schedule a later Cloud Task; that task re-downloads and prepares audio,
then reuses checkpoints instead of paying for completed transcription again.

One failed STT request after retries prevents embeddings/publishing. Empty VAD or all-empty STT
fails the video without fabricating text. Summarization finishes before transcript
rows are written, and publication uses the video-completion transaction.

The worker uses a separate 900-second timeout by default; the API stays at 300 seconds.
Download and VAD are repeated on quota continuation; long-video performance
and temporary-disk use must be benchmarked before increasing the production
duration setting. Anonymous videos are capped at 35 minutes.
Cancelled blocking FFmpeg/VAD work is joined before local cleanup; this may delay
cancellation handling and platform termination can still interrupt cleanup.

## Run

For a local listening-only preview (no STT), from the repository root:

```powershell
functions/venv/Scripts/python.exe -m pip install -r functions/requirements-vad.txt
functions/venv/Scripts/python.exe functions/app/pipeline/audio_chunker.py --audio "D:/audio/example.mp3"
```

`--audio` also accepts a local video file with an audio stream. It needs FFmpeg,
but no Google credentials, internet at inference time, or application secrets.
The installed Silero package includes the VAD model. The preview is optional;
normal API submissions automatically use VAD and sequential STT.

Alternatively set `LOCAL_AUDIO_PATH` near the top of `audio_chunker.py` and run
the file without arguments. `--youtube URL` or `YOUTUBE_URL` uses the existing
YouTube downloader and its Google cookie-secret permissions; the earlier 403
will still need to be resolved for that input mode. No cookie bypass is added.

Output: a unique directory under `functions/audio-preview.local/`, containing
playable mono 16 kHz WAV chunks and `manifest.json`. Files are excluded from Git
and Firebase uploads, and stay locally until manually removed. `--output PATH`
can choose a different output directory; its privacy/retention is your responsibility.

## Detection and merging

1. Decode to mono PCM at 16 kHz, keeping the original audio timeline.
2. Silero detects speech regions with a start threshold and lower negative
   threshold (hysteresis). Initial detection uses short silence boundaries and no
   padding so merge decisions use actual gaps.
3. Merge neighboring regions whose pause is <=600 ms, while the current group is
   below the 20-second soft target and the combined region plus padding fits the
   30-second cap. The last utterance may pass the soft target; the hard cap is
   never exceeded. Small pauses stay in the audio; regions are not concatenated
   or time-compressed.
4. A larger pause or size cap starts another chunk. Near the cap, Silero prefers
   its most suitable detected silence before a mechanical cut is needed. An
   individual uninterrupted speech region exceeding the cap is force-split with
   250 ms speech overlap. Each export also includes up to 150 ms padding at
   either end, so total overlap between forced-split exports can be 550 ms.
5. Save source hash, stable source/chunk UUIDs, sequence, raw speech regions,
   original sample/second bounds and forced-split flags in the manifest.

`.env` values (defaults apply when absent):

```dotenv
VAD_THRESHOLD=0.5
VAD_NEG_THRESHOLD=0.35
VAD_MIN_SPEECH_MS=250
VAD_MIN_SILENCE_MS=100
VAD_MERGE_PAUSE_MS=600
VAD_SPEECH_PAD_MS=150
VAD_MAX_CHUNK_SECONDS=30
VAD_GROUP_TARGET_SECONDS=20
VAD_SPLIT_OVERLAP_MS=250
VAD_MAX_AUDIO_SECONDS=2100
```

The 30-second cap includes padding. No-speech inputs produce an empty manifest,
not fabricated chunks. Oversized inputs are rejected rather than silently clipped.
Timestamp mapping is `video_time = chunk.start_seconds + local_word_time`.
Where two audio windows overlap, assembly assigns words by their midpoint to
one side of the overlap midpoint and clamps crossing word bounds at that seam.
Long removed silences remain gaps on the original video timeline. Repeated text
elsewhere is preserved. Missing chunk results and invalid timestamps fail assembly.
Independent STT timing/wording disagreement around a seam can still cause a
word omission/repetition; evaluate real speech before rollout.

VAD is probabilistic: evaluate quiet speech, music, Hindi/English and boundary
words by listening to generated files and comparing raw/merged regions. This
stage alone does not establish faster retrieval. Later stages can use chunk IDs
for durable queued STT, followed by bounded concurrency and measured ingestion latency.

Tests: from `functions`, run `venv/Scripts/python.exe -m unittest discover -s app/test -p "test_*.py" -v`.
Tests cover merge thresholds, boundaries, maximum size, overlap, stable IDs,
manifest/audio consistency, actual Silero inference on silence, sequential STT
calls, timestamp/overlap assembly and pipeline failure/cancellation behavior.
STT/provider responses are mocked: these tests do not measure live Groq quality,
quotas, cost or end-to-end latency. No deploy or live paid STT run is performed.

Detector API: [Silero VAD source](https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py).
Transcription API: [Groq word timestamps](https://console.groq.com/docs/api-reference).
