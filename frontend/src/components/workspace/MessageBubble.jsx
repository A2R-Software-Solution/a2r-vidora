export default function MessageBubble({ role, text, children }) {
  const isUser = role === "user";
  return (
    <div className={isUser ? "user-msg" : "ai-msg"}>
      {!isUser && <span className="ai-label">AI-generated answer</span>}
      <div className="message-text" dir="auto">{text}</div>
      {children}
    </div>
  );
}
