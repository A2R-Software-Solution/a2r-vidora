import { auth } from "../firebase";

// Every feature (analysis, questions, Shorts, Song Merger, downloads) needs an
// account. Action handlers call requireSignIn() first: a guest gets the
// sign-in dialog instead of a request the backend would refuse with 401.
export const SIGN_IN_REQUIRED = "Please sign in to use Vidora.";

let openSignIn = null;

export function setSignInOpener(open) {
  openSignIn = open;
}

export function isSignedIn() {
  return Boolean(auth.currentUser);
}

export function requireSignIn() {
  if (isSignedIn()) return true;
  openSignIn?.();
  return false;
}

// Opens the sign-in dialog when the backend refused a guest's action anyway.
export function handleSignInRequired(error) {
  if (error?.response?.status !== 401 || error.response.data?.detail !== SIGN_IN_REQUIRED) return false;
  openSignIn?.();
  return true;
}
