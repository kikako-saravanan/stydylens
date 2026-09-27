import { Fragment, ReactNode } from "react";

// Minimal renderer for the subset of Markdown the explanation uses
// (headings, bullet/numbered lists, **bold**, `code`) so we don't need a
// dependency. Text is rendered as React nodes, never as raw HTML.
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={i} className="rounded bg-surface-2 px-1 py-0.5 text-[0.9em]">{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function SimpleMarkdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag
        key={blocks.length}
        className={`my-2 space-y-1 pl-6 ${list.ordered ? "list-decimal" : "list-disc"}`}
      >
        {list.items.map((it, i) => (
          <li key={i}>{inline(it)}</li>
        ))}
      </Tag>
    );
    list = null;
  };

  for (const line of text.split("\n")) {
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);

    if (bullet || numbered) {
      const ordered = !!numbered;
      if (list && list.ordered !== ordered) flushList();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }
    flushList();
    if (heading) {
      blocks.push(
        <h4 key={blocks.length} className="mt-4 text-base font-semibold text-fg">
          {inline(heading[1])}
        </h4>
      );
    } else if (line.trim()) {
      blocks.push(
        <p key={blocks.length} className="my-2">
          {inline(line)}
        </p>
      );
    }
  }
  flushList();

  return <div className="text-base leading-7 text-fg">{blocks}</div>;
}
