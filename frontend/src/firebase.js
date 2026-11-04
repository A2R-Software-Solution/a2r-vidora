import { initializeApp } from "firebase/app";
import {
  browserLocalPersistence, browserSessionPersistence, getAuth, indexedDBLocalPersistence, initializeAuth,
} from "firebase/auth";

const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});

// Same persistence as getAuth(), minus the popup resolver: that loads Google's sign-in
// iframe on every page view, so AuthModal brings it along only when sign-in is opened.
export const auth = typeof window === "undefined" ? getAuth(app) : initializeAuth(app, {
  persistence: [indexedDBLocalPersistence, browserLocalPersistence, browserSessionPersistence],
});
