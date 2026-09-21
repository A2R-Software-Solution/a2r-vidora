import axios from "axios";
import { config } from "../config";
import { auth } from "../firebase";

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
  return request;
});

export default apiClient;
