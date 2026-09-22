const NAVIGATION_EVENT = "vidora:navigate";

export function getCurrentPath() {
  return window.location.pathname.replace(/\/+$/, "") || "/";
}

export function subscribeToNavigation(callback) {
  window.addEventListener("popstate", callback);
  window.addEventListener(NAVIGATION_EVENT, callback);
  return () => {
    window.removeEventListener("popstate", callback);
    window.removeEventListener(NAVIGATION_EVENT, callback);
  };
}

export function navigateTo(href) {
  if (href === window.location.pathname) {
    window.history.replaceState({ ...window.history.state, vidoraScroll: 0 }, "", href);
    window.scrollTo({ top: 0, behavior: "instant" });
    return;
  }
  window.history.replaceState({ ...window.history.state, vidoraScroll: window.scrollY }, "");
  window.history.pushState({ vidoraScroll: 0 }, "", href);
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}
