from maskrt.masking import find_placeholders, mask, unmask_robust, unmask_strict
from maskrt.spans import Detection, merge


def det(text: str, value: str, type_: str, source: str = "rules", nth: int = 0) -> Detection:
    start = -1
    for _ in range(nth + 1):
        start = text.index(value, start + 1)
    return Detection(start, start + len(value), type_, source)


def test_same_value_gets_same_placeholder():
    text = "Jana Weber schrieb. Später schrieb Jana Weber erneut an jana@example.org."
    dets = [det(text, "Jana Weber", "PERSON"), det(text, "Jana Weber", "PERSON", nth=1),
            det(text, "jana@example.org", "EMAIL")]
    r = mask(text, dets)
    assert r.masked == "[PERSON_1] schrieb. Später schrieb [PERSON_1] erneut an [EMAIL_1]."
    assert r.mapping == {"[PERSON_1]": "Jana Weber", "[EMAIL_1]": "jana@example.org"}


def test_numbering_is_per_type_and_in_order_of_appearance():
    text = "Anna Berg, Tom Kahl, anna@example.org, Anna Berg"
    dets = [det(text, "Anna Berg", "PERSON"), det(text, "Tom Kahl", "PERSON"),
            det(text, "anna@example.org", "EMAIL"), det(text, "Anna Berg", "PERSON", nth=1)]
    assert mask(text, dets).masked == "[PERSON_1], [PERSON_2], [EMAIL_1], [PERSON_1]"


def test_surname_alone_links_to_the_full_name():
    text = "Martin Koch kommt. Herr Koch bringt Kuchen."
    dets = [det(text, "Martin Koch", "PERSON"), det(text, "Koch", "PERSON", nth=1)]
    r = mask(text, dets)
    assert r.masked == "[PERSON_1] kommt. Herr [PERSON_1] bringt Kuchen."
    assert r.mapping["[PERSON_1]"] == "Martin Koch"  # the longest mention is put back


def test_ambiguous_first_name_gets_its_own_placeholder():
    text = "Anna Lehmann und Anna Petersen. Anna aus dem Vertrieb."
    dets = [det(text, "Anna Lehmann", "PERSON"), det(text, "Anna Petersen", "PERSON"),
            det(text, "Anna", "PERSON", nth=2)]
    assert mask(text, dets).masked == "[PERSON_1] und [PERSON_2]. [PERSON_3] aus dem Vertrieb."


def test_phone_numbers_in_different_spacing_are_one_value():
    text = "Ruf 0151 0482 3317 an, also 015104823317."
    dets = [det(text, "0151 0482 3317", "PHONE"), det(text, "015104823317", "PHONE")]
    assert mask(text, dets).masked == "Ruf [PHONE_1] an, also [PHONE_1]."


def test_overlapping_detections_are_merged_to_their_union():
    text = "Wohnt in Quittenweg 7, 34121 Kassel."
    rules = det(text, "Quittenweg 7, 34121 Kassel", "ADDRESS")
    ner = det(text, "Kassel", "LOCATION", source="ner")
    merged = merge([ner, rules])
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end, merged[0].type) == (rules.start, rules.end, "ADDRESS")
    assert merged[0].source == "rules+ner"
    partial = Detection(rules.start - 3, rules.start + 5, "PERSON", "ner")
    assert merge([rules, partial])[0].start == rules.start - 3


def test_masked_offsets_point_at_the_placeholders():
    text = "Hallo Jana Weber, Ihre IBAN DE91 9999 0001 0648 4898 90."
    dets = [det(text, "Jana Weber", "PERSON"), det(text, "DE91 9999 0001 0648 4898 90", "IBAN")]
    r = mask(text, dets)
    for rep in r.replacements:
        assert r.masked[rep.masked_start : rep.masked_end] == rep.placeholder
        assert text[rep.start : rep.end] in r.mapping[rep.placeholder]


def test_strict_unmasking_only_restores_exact_placeholders():
    mapping = {"[PERSON_1]": "Jana Weber", "[EMAIL_1]": "jana@example.org"}
    answer = "[PERSON_1] asks for a refund; contact [Person 1] at [EMAIL_1]."
    assert unmask_strict(answer, mapping) == "Jana Weber asks for a refund; contact [Person 1] at jana@example.org."


def test_robust_unmasking_restores_common_alterations():
    mapping = {"[PERSON_1]": "Jana Weber", "[PERSON_2]": "Tom Kahl", "[CUSTOMER_ID_1]": "KD-1"}
    answer = (
        "[Person 1] und [PERSON1] und PERSON_1 und (PERSON_2) und [ PERSON_2 ] und [person-2] "
        "und [CUSTOMER ID_1] und [PERSON_1]s Antrag."
    )
    restored = unmask_robust(answer, mapping)
    assert restored == (
        "Jana Weber und Jana Weber und Jana Weber und Tom Kahl und Tom Kahl und Tom Kahl "
        "und KD-1 und Jana Webers Antrag."
    )


def test_robust_unmasking_leaves_invented_placeholders_and_plain_prose():
    mapping = {"[PERSON_1]": "Jana Weber"}
    answer = "[PERSON_1] met [PERSON_3]. Person 1 in the table is someone else; Seite 2 folgt."
    assert unmask_robust(answer, mapping) == (
        "Jana Weber met [PERSON_3]. Person 1 in the table is someone else; Seite 2 folgt."
    )


def test_find_placeholders_marks_exact_and_altered():
    found = find_placeholders("[PERSON_1], [Person 1], [EMAIL_2]")
    assert [(f.placeholder, f.exact) for f in found] == [
        ("[PERSON_1]", True), ("[PERSON_1]", False), ("[EMAIL_2]", True)]


def test_round_trip_without_a_model_gives_back_the_original():
    text = "Hallo Jana Weber, Ihre IBAN DE91 9999 0001 0648 4898 90."
    dets = [det(text, "Jana Weber", "PERSON"), det(text, "DE91 9999 0001 0648 4898 90", "IBAN")]
    r = mask(text, dets)
    assert unmask_strict(r.masked, r.mapping) == text
    assert unmask_robust(r.masked, r.mapping) == text
