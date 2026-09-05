import TimestampChip from "./TimestampChip";

export default function SourceEvidence({ sources, onSeek }) {
  if (!Array.isArray(sources)) {
    return <p className="ai-notice">Source excerpts were not saved for this answer. Check the original video.</p>;
  }
  if (!sources.length) {
    return <p className="ai-notice">No matching transcript excerpts were found. This answer is not supported by retrieved context.</p>;
  }
  return (
    <details className="source-excerpts">
      <summary>Review {sources.length} retrieved excerpts</summary>
      {sources.map((source, index) => (
        <div key={index}>
          <TimestampChip startSeconds={source.start_time} endSeconds={source.end_time} onClick={onSeek} />
          <blockquote dir="auto">{source.text}</blockquote>
        </div>
      ))}
    </details>
  );
}
