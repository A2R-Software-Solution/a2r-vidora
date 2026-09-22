import { navigateTo } from "../../utils/siteNavigation";

export default function SiteLink({ href, onClick, children, ...props }) {
  return (
    <a {...props} href={href} onClick={(event) => {
      // Keep open-in-new-tab, downloads and hash links working like native links.
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
          props.target || props.download !== undefined || !href.startsWith("/") || href.startsWith("//")) return;
      onClick?.(event);
      if (event.defaultPrevented) return;
      event.preventDefault();
      navigateTo(href);
    }}>
      {children}
    </a>
  );
}
