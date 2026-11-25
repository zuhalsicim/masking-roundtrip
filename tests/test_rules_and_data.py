from maskrt import dataset
from maskrt.ner import split_at_newlines
from maskrt.rules import detect_rules, iban_checksum_ok


def found(text: str) -> list[tuple[str, str]]:
    return [(d.type, text[d.start : d.end]) for d in detect_rules(text)]


def test_structured_formats():
    text = (
        "Mail an t.brandl@firma.example, Tel. +49 160 0731 4482 oder (0421) 0 55 61 23, "
        "IBAN DE91 9999 0001 0648 4898 90, Kundennummer KD-2093-118, geb. 17.06.1989, "
        "Quittenweg 7, 34121 Kassel."
    )
    assert found(text) == [
        ("EMAIL", "t.brandl@firma.example"),
        ("PHONE", "+49 160 0731 4482"),
        ("PHONE", "(0421) 0 55 61 23"),
        ("IBAN", "DE91 9999 0001 0648 4898 90"),
        ("CUSTOMER_ID", "KD-2093-118"),
        ("DATE_OF_BIRTH", "17.06.1989"),
        ("ADDRESS", "Quittenweg 7, 34121 Kassel"),
    ]


def test_english_formats():
    text = "Ship to 1847 Maple Ridge Drive, Columbus, OH 43215, call (614) 555-0142, DOB 1999-04-12."
    assert found(text) == [
        ("ADDRESS", "1847 Maple Ridge Drive, Columbus, OH 43215"),
        ("PHONE", "(614) 555-0142"),
        ("DATE_OF_BIRTH", "1999-04-12"),
    ]


def test_numbers_that_are_not_personal_data():
    text = (
        "Rechnung 2026-0815 über 1.120,00 EUR, Termin am 01.12.2026, Version 7.4.2, ISO 27001, "
        "Tickets 88213 bis 88240, Art.-Nr. 310-22, 19 % USt., Raum 2.14."
    )
    assert found(text) == []


def test_a_date_is_a_date_of_birth_only_with_a_birth_word_before_it():
    assert found("Start am 01.12.2026.") == []
    assert found("Geburtsdatum laut Akte: 17.06.1989") == [("DATE_OF_BIRTH", "17.06.1989")]
    assert found("born 9 February 1979") == [("DATE_OF_BIRTH", "9 February 1979")]


def test_iban_checksum():
    assert iban_checksum_ok("DE54 9999 0001 0648 4898 90")
    assert not iban_checksum_ok("DE91 9999 0001 0648 4898 90")


def test_ner_entities_are_cut_at_line_breaks():
    text = "Present: Grace Baker\n- Will will mark"
    start = text.index("Grace")
    end = text.index("Will") + 4
    assert [text[s:e] for s, e in split_at_newlines(start, end, text)] == ["Grace Baker", "Will"]


def test_annotated_source_parses_into_offsets():
    docs = dataset.parse_annotated(
        "# comment\n=== x-1 | de | chat\nHallo [[PERSON#k:Martin Koch]], Herr [[PERSON#k:Koch]].\n"
    )
    assert len(docs) == 1
    d = docs[0]
    assert d.text == "Hallo Martin Koch, Herr Koch."
    assert [(d.text[s.start : s.end], s.entity) for s in d.spans] == [
        ("Martin Koch", "PERSON:k"), ("Koch", "PERSON:k")]


def test_test_set_matches_manifest_and_offsets():
    assert dataset.check_manifest() == []
    docs = dataset.load_documents()  # raises if a span does not match its text
    assert len(docs) == len(dataset.parse_annotated(dataset.ANNOTATED.read_text(encoding="utf-8")))
    assert {d.lang for d in docs} == {"de", "en"}


def test_no_iban_in_the_test_set_validates():
    ibans = [s.text for d in dataset.load_documents() for s in d.spans if s.type == "IBAN"]
    assert ibans and not any(iban_checksum_ok(i) for i in ibans)


def test_test_set_uses_only_reserved_mail_domains():
    mails = [s.text for d in dataset.load_documents() for s in d.spans if s.type == "EMAIL"]
    assert mails and all(m.rsplit(".", 1)[1] in {"example", "com", "org", "net"} for m in mails)
    assert all(m.endswith((".example", "@example.com", "@example.org", "@example.net")) for m in mails)
