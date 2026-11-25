import type { Segment, ViewerDocument } from "./types";

interface Mark {
  start: number;
  end: number;
  cls: string;
  title: string;
}

// Cut text into plain and highlighted pieces. Marks must not overlap.
export function cut(text: string, marks: Mark[]): Segment[] {
  const out: Segment[] = [];
  let pos = 0;
  for (const m of [...marks].sort((a, b) => a.start - b.start)) {
    if (m.start < pos) continue;
    if (m.start > pos) out.push({ text: text.slice(pos, m.start) });
    out.push({ text: text.slice(m.start, m.end), cls: m.cls, title: m.title });
    pos = m.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos) });
  return out;
}

// Original text: every hand label; red if any of it reached the model.
export function original(doc: ViewerDocument): Segment[] {
  const leaked = new Set(doc.leaked);
  return cut(
    doc.text,
    doc.spans.map((s) => {
      const value = doc.text.slice(s.start, s.end);
      const leak = leaked.has(value);
      return { start: s.start, end: s.end, cls: leak ? "leak" : "label", title: leak ? `${s.type}: leaked` : s.type };
    }),
  );
}

// Masked text: every placeholder, with the detector that found it.
export function masked(doc: ViewerDocument): Segment[] {
  return cut(
    doc.masked,
    doc.replacements.map((r) => ({
      start: r.masked_start,
      end: r.masked_end,
      cls: "placeholder",
      title: `found by ${r.source}`,
    })),
  );
}

// Same pattern as maskrt/masking.py ROBUST, simplified: any bracketed TYPE_N-like token.
const PLACEHOLDER_LIKE = /[[({<]\s*[A-Za-z][A-Za-z _-]*?[ _-]?\d{1,3}\s*[\])}>]|\b[A-Z][A-Z]+(?:_[A-Z]+)*_\d{1,3}\b/g;

// Model answer: exact placeholders, altered ones, invented ones.
export function answer(text: string, mapping: Record<string, string>, invented: string[]): Segment[] {
  const marks: Mark[] = [];
  for (const m of text.matchAll(PLACEHOLDER_LIKE)) {
    const token = m[0];
    const start = m.index ?? 0;
    let cls = "altered";
    let title = "altered placeholder";
    if (token in mapping) {
      cls = "placeholder";
      title = "exact placeholder";
    } else if (invented.includes(token)) {
      cls = "invented";
      title = "placeholder the model invented";
    }
    marks.push({ start, end: start + token.length, cls, title });
  }
  return cut(text, marks);
}

// Restored answer: every value put back, and anything placeholder-like that is left.
export function restored(text: string, mapping: Record<string, string>): Segment[] {
  const marks: Mark[] = [];
  const values = [...new Set(Object.values(mapping))].sort((a, b) => b.length - a.length);
  for (const v of values) {
    let i = text.indexOf(v);
    while (i >= 0) {
      if (!marks.some((m) => i < m.end && m.start < i + v.length)) {
        marks.push({ start: i, end: i + v.length, cls: "label", title: "value put back" });
      }
      i = text.indexOf(v, i + v.length);
    }
  }
  for (const m of text.matchAll(PLACEHOLDER_LIKE)) {
    const start = m.index ?? 0;
    marks.push({ start, end: start + m[0].length, cls: "leak", title: "not restored" });
  }
  return cut(text, marks);
}
