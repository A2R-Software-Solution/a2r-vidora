export default function MessageBubble({ role, text, children }) {
  const isUser = role === "user";

  return (
    <div className={isUser ? "user-msg" : "ai-msg"}>
      {text}
      {children}
    </div>
  );
}