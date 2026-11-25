// The shape of results/viewer.json, written by `python -m maskrt export`.

export interface LabelledSpan {
  start: number;
  end: number;
  type: string;
}

export interface Replacement {
  start: number;
  end: number;
  masked_start: number;
  masked_end: number;
  placeholder: string;
  source: string;
}

export interface Answer {
  answer: string;
  restored_strict: string;
  restored_robust: string;
  altered_forms: string[];
  invented_forms: string[];
}

export interface ViewerDocument {
  id: string;
  lang: string;
  kind: string;
  text: string;
  spans: LabelledSpan[];
  masked: string;
  mapping: Record<string, string>;
  replacements: Replacement[];
  leaked: string[];
  answers: Record<string, Answer>;
}

export interface ViewerData {
  dataset_version: string;
  detector: string;
  documents: ViewerDocument[];
}

// A piece of text and, if it is highlighted, the CSS class and a tooltip.
export interface Segment {
  text: string;
  cls?: string;
  title?: string;
}
