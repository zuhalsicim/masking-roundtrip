from maskrt.survival import analyse_answer, summarise_survival

MAPPING = {"[PERSON_1]": "Jana Weber", "[PERSON_2]": "Tom Kahl", "[EMAIL_1]": "jana@example.org"}


def test_classifies_exact_altered_invented_and_dropped():
    answer = "[PERSON_1] schreibt an [Person 2]; [PERSON_3] ist neu."
    r = analyse_answer(answer, MAPPING, [])
    assert (r["exact"], r["altered"], r["invented"], r["dropped"]) == (1, 1, 1, 1)
    assert r["altered_forms"] == ["[Person 2]"]
    assert r["invented_forms"] == ["[PERSON_3]"]
    assert r["left_after_strict"] == 2  # [Person 2] and [PERSON_3]
    assert r["left_after_robust"] == 1  # only the invented one
    assert r["restored_robust"] == "Jana Weber schreibt an Tom Kahl; [PERSON_3] ist neu."


def test_placeholder_made_up_from_a_leaked_name_counts_as_invented():
    r = analyse_answer("[PERSON_1] and [HERR_Nguyen] check the tickets.", MAPPING, [])
    assert (r["exact"], r["invented"], r["invented_forms"]) == (1, 1, ["[HERR_Nguyen]"])
    assert r["left_after_robust"] == 1


def test_leaked_value_repeated_by_the_model_is_counted():
    r = analyse_answer("Jana Weber asked for a refund.", MAPPING, ["Jana Weber", "0151"])
    assert r["leaked_values_in_answer"] == ["Jana Weber"]


def test_summary_counts_answers_restored_before_and_after():
    rows = [
        analyse_answer("[PERSON_1] and [EMAIL_1].", MAPPING, []),
        analyse_answer("[Person 1] and [EMAIL_1].", MAPPING, []),
        analyse_answer("[PERSON_9].", MAPPING, []),
    ]
    s = summarise_survival(rows)
    assert s["answers"] == 3
    assert (s["exact"], s["altered"], s["invented"]) == (3, 1, 1)
    assert s["answers_fully_restored_strict"] == 1
    assert s["answers_fully_restored_robust"] == 2
