const BUG_REPORT_URL = "https://forms.gle/Xw7KJ5noMo2DFTRd6";

export default function BugReportButton() {
  return (
    <a
      className="bug-report-button"
      href={BUG_REPORT_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Report a bug"
      title="Report a bug"
      data-tooltip="Facing an issue?"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 8.5V6a3 3 0 0 1 6 0v2.5M8 11H5m14 0h-3M8.5 7.5 6.5 5.5m9 2 2-2M9 20h6a3 3 0 0 0 3-3v-5.5a3 3 0 0 0-3-3h-6a3 3 0 0 0-3 3V17a3 3 0 0 0 3 3Zm1-7h.01M13.5 13h.01M12 16h.01" />
      </svg>
    </a>
  );
}
