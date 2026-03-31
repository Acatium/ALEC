import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useReport, useEngagement } from "../api/hooks";

/** Minimal markdown-to-HTML converter for the report. */
function markdownToHtml(md: string): string {
  let html = md
    // Escape HTML
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // Headers
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Tables
    .replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match
        .split("|")
        .filter((c) => c.trim() !== "")
        .map((c) => c.trim());
      // Check if separator row
      if (cells.every((c) => /^-+$/.test(c))) return "";
      const tag = "td";
      return `<tr>${cells.map((c) => `<${tag}>${c}</${tag}>`).join("")}</tr>`;
    })
    // Unordered lists
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    // Paragraphs (blank lines)
    .replace(/\n\n/g, "</p><p>")
    // Line breaks
    .replace(/\n/g, "<br/>");

  // Wrap in paragraph
  html = `<p>${html}</p>`;

  // Wrap consecutive <li> in <ul>
  html = html.replace(
    /(<li>.*?<\/li>(<br\/>)?)+/g,
    (match) => `<ul>${match.replace(/<br\/>/g, "")}</ul>`,
  );

  // Wrap consecutive <tr> in <table>
  html = html.replace(
    /(<tr>.*?<\/tr>(<br\/>)?)+/g,
    (match) =>
      `<table class="report-table">${match.replace(/<br\/>/g, "")}</table>`,
  );

  // Clean empty paragraphs
  html = html.replace(/<p><\/p>/g, "");
  html = html.replace(/<p><br\/><\/p>/g, "");

  return html;
}

export default function ReportView() {
  const { id } = useParams<{ id: string }>();
  const [enabled, setEnabled] = useState(true);
  const { data: report, isLoading } = useReport(id ?? "", enabled);
  const { data: engagement } = useEngagement(id ?? "");

  if (!id) return <p className="text-sm text-red-600">Missing engagement ID</p>;

  const handleCopy = async () => {
    if (report?.markdown) {
      await navigator.clipboard.writeText(report.markdown);
    }
  };

  const handleDownload = () => {
    if (!report?.markdown) return;
    const blob = new Blob([report.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.title || "report"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      {/* Nav */}
      <div className="flex items-center gap-3">
        <Link
          to={`/engagements/${id}`}
          className="text-sm text-indigo-600 hover:text-indigo-800"
        >
          &larr; Back to Dashboard
        </Link>
        {engagement && (
          <span className="text-sm text-gray-500 truncate">
            {engagement.name}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {!enabled && (
          <button
            onClick={() => setEnabled(true)}
            className="rounded bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700"
          >
            Generate Report
          </button>
        )}
        {report && (
          <>
            <button
              onClick={handleCopy}
              className="rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              Copy Markdown
            </button>
            <button
              onClick={handleDownload}
              className="rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              Download .md
            </button>
            <button
              onClick={() => window.print()}
              className="rounded border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
            >
              Print
            </button>
          </>
        )}
      </div>

      {isLoading && (
        <p className="text-sm text-gray-500">Generating report...</p>
      )}

      {/* Report content */}
      {report && (
        <div
          className="report-content prose prose-sm max-w-none rounded-lg border border-gray-200 bg-white p-8"
          dangerouslySetInnerHTML={{ __html: markdownToHtml(report.markdown) }}
        />
      )}

      {/* Print styles */}
      <style>{`
        @media print {
          nav, .flex.items-center.gap-2, .flex.items-center.gap-3 { display: none !important; }
          .report-content { border: none !important; padding: 0 !important; }
        }
        .report-table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }
        .report-table td { border: 1px solid #e5e7eb; padding: 0.25rem 0.5rem; font-size: 0.875rem; }
        .report-table tr:first-child td { font-weight: 600; background: #f9fafb; }
      `}</style>
    </div>
  );
}
