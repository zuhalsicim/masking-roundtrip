from maskrt.dataset import Document, Span
from maskrt.masking import mask
from maskrt.metrics import bootstrap, consistency, leak_rate, score_document, summarise
from maskrt.spans import Detection


def doc_with(text: str, labels: list[tuple[str, str]], doc_id: str = "d1", lang: str = "de") -> Document:
    spans, pos = [], 0
    for value, type_ in labels:
        start = text.index(value, pos)
        spans.append(Span(start, start + len(value), type_, value, f"{type_}:{value.casefold()}"))
        pos = start + len(value)
    return Document(doc_id, lang, "test", text, spans)


TEXT = "Jana Weber, Tel. 0151 0482 3317, wohnt in Kassel."
DOC = doc_with(TEXT, [("Jana Weber", "PERSON"), ("0151 0482 3317", "PHONE")])


def at(value: str, type_: str, source: str = "rules") -> Detection:
    s = TEXT.index(value)
    return Detection(s, s + len(value), type_, source)


def test_fully_masked_span_is_protected_and_partial_one_leaks():
    s = score_document(DOC, [at("Jana Weber", "PERSON"), at("0151 0482", "PHONE")])
    assert [ok for _, ok in s.spans] == [True, False]
    assert s.leaked == 1


def test_whitespace_inside_a_span_does_not_need_masking():
    two = [at("0151", "PHONE"), at("0482 3317", "PHONE")]  # the space between is not masked
    s = score_document(DOC, two + [at("Jana Weber", "PERSON")])
    assert s.leaked == 0


def test_detection_outside_labels_is_over_masking():
    s = score_document(DOC, [at("Kassel", "LOCATION", "ner"), at("Jana Weber", "PERSON")])
    assert sorted(ok for _, ok in s.detections) == [False, True]


def test_detection_counts_as_correct_if_half_of_it_is_labelled():
    # "Weber, Tel." : 5 labelled characters of 10 non-space characters -> correct
    s = score_document(DOC, [at("Weber, Tel.", "PERSON")])
    assert [ok for _, ok in s.detections] == [True]
    s = score_document(DOC, [at("Weber, Tel. 0", "PERSON")])  # 6 labelled of 11
    assert [ok for _, ok in s.detections] == [True]
    s = score_document(DOC, [at("r, Tel.", "PERSON")])  # 1 labelled of 6
    assert [ok for _, ok in s.detections] == [False]


def test_summary_per_type_and_language():
    other = doc_with("Mail: a@example.org", [("a@example.org", "EMAIL")], doc_id="d2", lang="en")
    scores = [score_document(DOC, [at("Jana Weber", "PERSON")]), score_document(other, [])]
    s = summarise(scores, n_boot=200)
    assert s["labelled_spans"] == 3 and s["leaked_spans"] == 2
    assert s["recall"]["PERSON"]["recall"] == 1.0
    assert s["recall"]["PHONE"]["recall"] == 0.0
    assert s["recall"]["ALL|en"] == {"protected": 0, "labelled": 1, "recall": 0.0}
    assert s["documents_with_leak"] == 2
    assert s["precision"]["PERSON"]["precision"] == 1.0


def test_bootstrap_interval_contains_the_estimate_and_is_reproducible():
    docs = [doc_with(f"Name {i}: Jana Weber", [("Jana Weber", "PERSON")], doc_id=f"d{i}") for i in range(20)]
    scores = []
    for i, d in enumerate(docs):
        s = d.spans[0]
        found = [] if i % 4 == 0 else [Detection(s.start, s.end, "PERSON", "rules")]  # every 4th leaks
        scores.append(score_document(d, found))
    rate = leak_rate(scores)
    assert rate == 5 / 20
    lo, hi = bootstrap(scores, leak_rate, n=500, seed=1)
    assert lo <= rate <= hi
    assert (lo, hi) == bootstrap(scores, leak_rate, n=500, seed=1)
    assert bootstrap([scores[1]] * 5, leak_rate, n=50) == (0.0, 0.0)


def test_consistency_finds_split_and_merged_people():
    text = "Anna Lehmann und Anna Petersen. Anna aus dem Vertrieb. Joy Fisher und Mr Fisher."
    doc = Document("d", "de", "test", text, [
        Span(0, 12, "PERSON", "Anna Lehmann", "PERSON:lehmann"),
        Span(17, 30, "PERSON", "Anna Petersen", "PERSON:petersen"),
        Span(32, 36, "PERSON", "Anna", "PERSON:petersen"),
        Span(55, 65, "PERSON", "Joy Fisher", "PERSON:joy"),
        Span(73, 79, "PERSON", "Fisher", "PERSON:father"),
    ])
    dets = [Detection(s.start, s.end, "PERSON", "ner") for s in doc.spans]
    c = consistency(doc, mask(text, dets).replacements)
    assert c["people_with_several_mentions"] == 1
    assert c["split"] == ["PERSON:petersen"]  # "Anna" is ambiguous, gets [PERSON_3]
    assert c["merged"] == ["[PERSON_4]"]  # "Fisher" is linked to "Joy Fisher", but is her father
