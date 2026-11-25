"""How placeholders come back from the model, and whether unmasking puts the right values back."""

from __future__ import annotations

from .masking import find_placeholders, unmask_robust, unmask_strict


def analyse_answer(answer: str, mapping: dict[str, str], leaked_values: list[str]) -> dict:
    """Classify every placeholder-like token in one answer.

    exact:        [PERSON_1] as sent
    altered:      [Person 1], [PERSON1], PERSON_1, (PERSON_1) ... for a placeholder that was sent
    invented:     a placeholder that was not sent, e.g. [PERSON_3] when there were two people
    dropped:      placeholders that were sent but do not appear in the answer at all
                  (not an error in itself: a summary may leave a person out)
    left_strict / left_robust: placeholder-like tokens still in the text after unmasking
    """
    found = find_placeholders(answer)
    sent = set(mapping)
    exact = [f for f in found if f.exact and f.placeholder in sent]
    altered = [f for f in found if not f.exact and f.placeholder in sent]
    invented = [f for f in found if f.placeholder not in sent]
    present = {f.placeholder for f in found if f.placeholder in sent}
    strict = unmask_strict(answer, mapping)
    robust = unmask_robust(answer, mapping)
    left_strict = find_placeholders(strict)
    left_robust = find_placeholders(robust)
    return {
        "sent": len(sent),
        "exact": len(exact),
        "altered": len(altered),
        "altered_forms": sorted({answer[f.start : f.end] for f in altered}),
        "invented": len(invented),
        "invented_forms": sorted({answer[f.start : f.end] for f in invented}),
        "dropped": len(sent - present),
        "left_after_strict": len(left_strict),
        "left_after_robust": len(left_robust),
        "restored_strict": strict,
        "restored_robust": robust,
        # Values that leaked into the masked text and came back in the answer unmasked.
        "leaked_values_in_answer": sorted({v for v in leaked_values if v and v in answer}),
    }


def summarise_survival(rows: list[dict]) -> dict:
    """Totals over all answers of one prompt variant."""
    occ = sum(r["exact"] + r["altered"] + r["invented"] for r in rows)
    n = len(rows)

    def share(k: int, d: int) -> float | None:
        return None if d == 0 else k / d

    exact = sum(r["exact"] for r in rows)
    altered = sum(r["altered"] for r in rows)
    invented = sum(r["invented"] for r in rows)
    clean_strict = sum(r["left_after_strict"] == 0 for r in rows)
    clean_robust = sum(r["left_after_robust"] == 0 for r in rows)
    return {
        "answers": n,
        "placeholders_sent": sum(r["sent"] for r in rows),
        "placeholder_tokens_in_answers": occ,
        "exact": exact,
        "altered": altered,
        "invented": invented,
        "exact_share": share(exact, occ),
        "altered_share": share(altered, occ),
        "invented_share": share(invented, occ),
        "sent_but_dropped": sum(r["dropped"] for r in rows),
        "answers_with_altered": sum(r["altered"] > 0 for r in rows),
        "answers_with_invented": sum(r["invented"] > 0 for r in rows),
        "answers_fully_restored_strict": clean_strict,
        "answers_fully_restored_robust": clean_robust,
        "answers_fully_restored_strict_share": share(clean_strict, n),
        "answers_fully_restored_robust_share": share(clean_robust, n),
        "tokens_left_after_strict": sum(r["left_after_strict"] for r in rows),
        "tokens_left_after_robust": sum(r["left_after_robust"] for r in rows),
        "answers_repeating_a_leaked_value": sum(bool(r["leaked_values_in_answer"]) for r in rows),
    }
