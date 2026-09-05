export default function ProcessingNotice() {
  return (
    <aside className="processing-notice" aria-label="How AI processes your data">
      <p id="processing-notice"><strong>Before you analyze:</strong> video audio is sent to Groq for transcription.
        Questions and transcript excerpts are also sent to Groq to generate answers and summaries.
        Only submit videos you are authorized to process; avoid sharing sensitive personal information.</p>
      <details>
        <summary>Data storage and AI limitations</summary>
        <p>Vidora temporarily stores transcripts, embeddings, summaries, and Q&amp;A history.
          Analysis data is scheduled for cleanup after its expiry; the workspace shows the expiry time.
          Downloaded media is removed after processing. External providers have their own retention practices.</p>
        <p>AI can mishear speech, miss context, and produce incorrect statements.
          Accuracy can vary across languages and accents. Language-specific quality has not yet been validated.
          Check the original video before relying on an answer.</p>
        <p>Vidora is for understanding video content with human review. Do not use its output alone
          to make decisions affecting someone’s health, safety, rights, or access to services.</p>
        <p>The embedded player connects to YouTube. The video reference may be saved in this browser to support reopening it.</p>
      </details>
    </aside>
  );
}
