import { useId, useState } from "react";

export default function IssueReport({ videoId, answerId, outputType = "answer" }) {
  const id = useId();
  const [category, setCategory] = useState("Incorrect or unsupported information");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("");

  const download = (event) => {
    event.preventDefault();
    const report = {
      type: "vidora-ai-issue", created_at: new Date().toISOString(),
      video_id: videoId, answer_id: answerId ?? null, output_type: outputType,
      category, note: note.trim(),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "vidora-issue-report.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStatus("Report prepared for download. It has not been sent to Vidora. Share it with your service operator for review.");
  };

  return (
    <details className="issue-report">
      <summary>Flag an issue with this {outputType}</summary>
      <form onSubmit={download}>
        <p>Create a report to share with your service operator. Reports are downloaded to your device;
          there is no in-app submission service yet. Video content and your question are not included automatically.</p>
        <label htmlFor={`${id}-category`}>Issue type</label>
        <select id={`${id}-category`} value={category} onChange={(event) => setCategory(event.target.value)}>
          <option>Incorrect or unsupported information</option>
          <option>Harmful or biased content</option>
          <option>Privacy concern</option>
          <option>Language or transcription problem</option>
          <option>Other issue</option>
        </select>
        <label htmlFor={`${id}-note`}>Details (optional; avoid sensitive personal information)</label>
        <textarea dir="auto" id={`${id}-note`} value={note} maxLength={2000} rows={3}
          onChange={(event) => setNote(event.target.value)} />
        <button type="submit" className="secondary-button">Download issue report</button>
        <p role="status">{status}</p>
      </form>
    </details>
  );
}
