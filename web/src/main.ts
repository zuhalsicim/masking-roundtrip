import "./style.css";
import data from "../../results/viewer.json";
import { answer, masked, original, restored } from "./segments";
import type { Segment, ViewerData, ViewerDocument } from "./types";

// The JSON is written by the Python side; its shape is described in types.ts.
const results = data as unknown as ViewerData;
const docSelect = document.querySelector<HTMLSelectElement>("#doc")!;
const variantSelect = document.querySelector<HTMLSelectElement>("#variant")!;
const panes = document.querySelector<HTMLElement>("#panes")!;
const legend = document.querySelector<HTMLElement>("#legend")!;

function render(segments: Segment[]): HTMLElement {
  const pre = document.createElement("pre");
  for (const s of segments) {
    if (!s.cls) {
      pre.append(s.text);
      continue;
    }
    const mark = document.createElement("mark");
    mark.className = s.cls;
    mark.textContent = s.text;
    if (s.title) mark.title = s.title;
    pre.append(mark);
  }
  return pre;
}

function pane(title: string, note: string, segments: Segment[]): HTMLElement {
  const section = document.createElement("section");
  const h = document.createElement("h2");
  h.textContent = title;
  const p = document.createElement("p");
  p.className = "note";
  p.textContent = note;
  section.append(h, p, render(segments));
  return section;
}

function show(doc: ViewerDocument, variant: string): void {
  const a = doc.answers[variant];
  const leaks = doc.leaked.length ? `${doc.leaked.length} labelled value(s) reached the model` : "nothing leaked";
  panes.replaceChildren(
    pane("Original", `${doc.id}, ${doc.lang}, ${doc.kind}: hand labels (${leaks})`, original(doc)),
    pane("Masked, as sent to the model", `detector: ${results.detector}`, masked(doc)),
    ...(a
      ? [
          pane(
            "Model answer",
            `altered: ${a.altered_forms.join(", ") || "none"}; invented: ${a.invented_forms.join(", ") || "none"}`,
            answer(a.answer, doc.mapping, a.invented_forms),
          ),
          pane("Restored answer (robust unmasking)", "values put back from the mapping", restored(a.restored_robust, doc.mapping)),
        ]
      : [pane("Model answer", "no model answer in the results", [])]),
  );
}

function init(): void {
  for (const d of results.documents) docSelect.add(new Option(`${d.id} (${d.kind})`, d.id));
  const variants = Object.keys(results.documents[0]?.answers ?? {});
  for (const v of variants) variantSelect.add(new Option(v, v));
  legend.innerHTML =
    'Test set version <code></code>. <mark class="label">labelled or restored value</mark> ' +
    '<mark class="leak">leaked or not restored</mark> <mark class="placeholder">placeholder</mark> ' +
    '<mark class="altered">altered placeholder</mark> <mark class="invented">invented placeholder</mark>';
  legend.querySelector("code")!.textContent = results.dataset_version;
  const update = () => {
    const doc = results.documents.find((d) => d.id === docSelect.value);
    if (doc) show(doc, variantSelect.value);
  };
  docSelect.addEventListener("change", update);
  variantSelect.addEventListener("change", update);
  update();
}

init();
