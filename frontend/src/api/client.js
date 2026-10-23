import axios from "axios";
import { config } from "../config";
import { auth } from "../firebase";
import { guestId } from "../utils/guestId";

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
    return Promise.reject(error);
  }
);

apiClient.interceptors.request.use(async (request) => {
  const user = auth.currentUser;
  if (user) request.headers.Authorization = `Bearer ${await user.getIdToken()}`;
  // The warm-up ping stays header-free so it needs no CORS preflight.
  const id = request.params?.warmup ? null : guestId();
  if (id) request.headers["X-Guest-Id"] = id;
  return request;
});

export default apiClient;
