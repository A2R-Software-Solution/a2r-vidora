import { useState } from "react";
import { GoogleAuthProvider, createUserWithEmailAndPassword, signInWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { auth } from "../../firebase";
import { createOrGetUser } from "../../api/userApi";

async function registerProfile(user) {
  if (!user?.email) throw new Error("Your sign-in provider did not provide an email address.");
  await createOrGetUser({ firebase_uid: user.uid, email: user.email });
}

export default function AuthModal({ onClose }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async (operation) => {
    setLoading(true);
    setError("");
    try {
      await operation();
      onClose();
    } catch (err) {
      setError(err?.message?.replace("Firebase: ", "") || "Sign-in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const submit = (event) => {
    event.preventDefault();
    run(async () => {
      const credential = mode === "signup"
        ? await createUserWithEmailAndPassword(auth, email, password)
        : await signInWithEmailAndPassword(auth, email, password);
      await registerProfile(credential.user);
    });
  };

  return <div className="auth-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="auth-modal" role="dialog" aria-modal="true" aria-label="Account access" onMouseDown={(event) => event.stopPropagation()}>
      <button className="auth-close" type="button" onClick={onClose} aria-label="Close">×</button>
      <h2>{mode === "signup" ? "Create your account" : "Welcome back"}</h2>
      <p>{mode === "signup" ? "Sign up to analyze videos longer than 35 minutes." : "Sign in to continue your analyses."}</p>
      <button className="google-auth" type="button" disabled={loading} onClick={() => run(async () => {
        const credential = await signInWithPopup(auth, new GoogleAuthProvider());
        await registerProfile(credential.user);
      })}>
        <svg className="google-auth-mark" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
          <path fill="#EA4335" d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.482h4.844c-.209 1.125-.842 2.078-1.796 2.716v2.258h2.909c1.702-1.567 2.683-3.874 2.683-6.615z" />
          <path fill="#4285F4" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.909-2.258c-.806.54-1.837.859-3.047.859-2.344 0-4.328-1.584-5.037-3.71H.956v2.332A9 9 0 0 0 9 18z" />
          <path fill="#FBBC05" d="M3.963 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.281-1.71V4.958H.956A9 9 0 0 0 0 9c0 1.452.348 2.827.956 4.042l3.007-2.332z" />
          <path fill="#34A853" d="M9 3.58c1.322 0 2.507.455 3.44 1.346l2.581-2.581C13.463.891 11.43 0 9 0A9 9 0 0 0 .956 4.958L3.963 7.29C4.672 5.164 6.656 3.58 9 3.58z" />
        </svg>
        <span>Continue with Google</span>
      </button>
      <div className="auth-divider"><span>or</span></div>
      <form onSubmit={submit}>
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" autoComplete="email" required />
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password (6+ characters)" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength="6" required />
        {error && <div className="error-text">{error}</div>}
        <button className="auth-primary" disabled={loading}>{loading ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}</button>
      </form>
      <button className="auth-switch" type="button" onClick={() => { setMode(mode === "signup" ? "login" : "signup"); setError(""); }}>
        {mode === "signup" ? "Already have an account? Sign in" : "New here? Create an account"}
      </button>
    </section>
  </div>;
}
