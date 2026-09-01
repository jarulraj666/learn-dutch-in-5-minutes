// Renders passage content_nl as plain paragraphs, except for runs of pipe-delimited
// lines (e.g. "Tarieven:" price grids), which are rendered as an HTML table. Table rows
// can be preceded/followed by ordinary text on adjacent lines within the same paragraph.
type Segment = { type: "text"; content: string } | { type: "table"; rows: string[][] };

function colCount(line: string): number {
  return line.includes("|") ? line.split("|").length : 0;
}

function parseSegments(text: string): Segment[] {
  const lines = text.split("\n");
  const segments: Segment[] = [];
  let buffer: string[] = [];

  const flushText = () => {
    if (buffer.length > 0) {
      segments.push({ type: "text", content: buffer.join("\n") });
      buffer = [];
    }
  };

  let i = 0;
  while (i < lines.length) {
    const cols = colCount(lines[i]);
    if (cols >= 2) {
      const runCols = cols;
      const rows: string[][] = [];
      while (i < lines.length && colCount(lines[i]) === runCols) {
        rows.push(lines[i].split("|").map((cell) => cell.trim()));
        i++;
      }
      if (rows.length >= 2) {
        flushText();
        segments.push({ type: "table", rows });
        continue;
      }
      // Single matching line was a false positive (e.g. incidental "|"); treat as text.
      buffer.push(rows[0].join(" | "));
      continue;
    }
    buffer.push(lines[i]);
    i++;
  }
  flushText();
  return segments;
}

export function PassageContent({ text }: { text: string }) {
  const segments = parseSegments(text);

  return (
    <div className="space-y-3">
      {segments.map((segment, i) => {
        if (segment.type === "table") {
          const [header, ...body] = segment.rows;
          return (
            <table key={i} className="w-full text-sm border-collapse">
              <thead>
                <tr>
                  {header.map((cell, j) => (
                    <th key={j} className="border border-slate-200 bg-slate-50 px-2 py-1 text-left font-semibold">
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) => (
                      <td key={c} className="border border-slate-200 px-2 py-1">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap text-slate-700">
            {segment.content}
          </p>
        );
      })}
    </div>
  );
}
