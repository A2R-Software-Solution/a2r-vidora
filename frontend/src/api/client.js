import axios from "axios";
import { config } from "../config";
import { auth } from "../firebase";
import { handleSignInRequired } from "../utils/authGate";
import { isBanError, showBanNotice } from "../utils/banNotice";

const apiClient = axios.create({
  baseURL: config.apiBaseUrl,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error?.response?.data || error.message);
    // A banned account sees the admin's message, whatever it was doing.
    if (isBanError(error)) showBanNotice(error.response.data.reason);
    // Only an action the user clicked opens the dialog, never a background read.
    if (error?.config?.method !== "get") handleSignInRequired(error);
    return Promise.reject(error);
  }
);

apiClient.interceptors.request.use(async (request) => {
  const user = auth.currentUser;
  if (user) request.headers.Authorization = `Bearer ${await user.getIdToken()}`;
  return request;
});

export default apiClient;
