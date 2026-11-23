import { config } from "../config";

let loading = null;

// Loads the YouTube iframe API once and resolves with window.YT. Safe next to
// the main player, which may already be loading the same script.
export function loadYouTubeApi() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!loading) {
    loading = new Promise((resolve) => {
      const previous = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = () => {
        if (typeof previous === "function") previous();
        resolve(window.YT);
      };
      if (!document.querySelector(`script[src="${config.youtubePlayerScriptUrl}"]`)) {
        const tag = document.createElement("script");
        tag.src = config.youtubePlayerScriptUrl;
        document.body.appendChild(tag);
      }
    });
  }
  return loading;
}
