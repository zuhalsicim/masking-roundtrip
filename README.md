# masking-roundtrip

## Kurzfassung

Bevor ein Text an ein Sprachmodell geht, werden personenbezogene Daten durch nummerierte Platzhalter ersetzt (`[PERSON_1]`, `[IBAN_1]`); in der Antwort des Modells werden die echten Werte wieder eingesetzt. Dieses Repository misst beide Hälften an 48 erfundenen deutschen und englischen Geschäftstexten mit 176 von Hand markierten Werten.

- **Erkennung:** Regeln allein lassen 51,7 % der markierten Werte durch (alle Namen), die spaCy-Modelle allein 59 bis 60 % (fast alle strukturierten Daten). Kombiniert gehen noch **14 von 176 Werten (8,0 %, 95-%-Intervall 4,0 bis 12,2 %)** unmaskiert an das Modell, alles Namen: Namen, die zugleich Wörter sind (Sommer, Bauer, Mark, Grace), allein stehende Vor- und Nachnamen, klein geschriebene Namen im Chat und ein voller Name. Der Preis: 65 von 222 maskierten Stellen sind keine personenbezogenen Daten.
- **Rundreise:** Qwen2.5-1.5B-Instruct (Q4_K_M, llama.cpp, CPU) gibt 95,1 % der Platzhalter unverändert zurück, mit einer Anweisung im Prompt 98,7 %. Ohne Anweisung stellt strenges Zurücksetzen 45 von 48 Antworten vollständig wieder her, tolerantes 47 von 48; mit Anweisung beide 46 von 48. Was bleibt, sind Platzhalter, die das Modell selbst erfindet.
- **Grenzen:** erfundene Daten, Regeln und Testtexte von derselben Person, 48 Texte, ein kleines Modell. Die Zahlen beschreiben diesen Aufbau, nicht Erkennung im Allgemeinen.

## The question

A text is masked before it reaches a language model: names, e-mail addresses, IBANs and so on are replaced by numbered placeholders such as `[PERSON_1]`. The model answers on the masked text, and the real values are put back into its answer. Two things can go wrong:

1. **Leakage.** The detector misses a value, and it reaches the model unmasked.
2. **A broken round trip.** The model changes a placeholder (`[Person 1]`, `PERSON_1`), drops it or invents a new one, and the value cannot be put back.

How often does each happen, for which kinds of data, and what helps?

## How it works

```
text ──> detectors ──> merge overlaps ──> mask ──> model ──> answer ──> unmask ──> restored answer
          rules                           [PERSON_1] -> "Jana Kowalczyk"  (mapping stays here)
          spaCy NER
```

- **Detectors** (`maskrt/rules.py`, `maskrt/ner.py`)
  - `rules`: regular expressions for e-mail, IBAN (shape only, see Limits), phone numbers, dates of birth (a date with a birth word such as "geb.", "born" or "DOB" shortly before it), customer and employee numbers (after a keyword such as "Kundennummer" or "staff number"), German and British/US postal addresses.
  - `ner_multi`: spaCy `xx_ent_wiki_sm` 3.8.0, one model for every language. Masks PER and LOC.
  - `ner_lang`: spaCy `de_core_news_sm` 3.8.0 for German, `en_core_web_sm` 3.8.0 for English, chosen by the language field of the test set. Masks PERSON, PER, LOC, GPE and FAC.
  - `combined`: all three together.
  Company names (ORG) are not masked. Entities from the spaCy models are cut at line breaks; this was added after the first run, where "Grace Baker" and "- Will" on the next line came out as one entity.
- **Masking** (`maskrt/masking.py`): overlapping detections are merged into their union (masking more never leaks more). Placeholders are numbered per type in order of appearance. The same value gets the same placeholder within a document; phone numbers, IBANs and IDs are compared without spaces. A name that is part of exactly one earlier name ("Koch" after "Martin Koch") gets the earlier name's placeholder; with two candidates ("Anna" after "Anna Lehmann" and "Anna Petersen") it gets a new one. The mapping from placeholder to value stays with the caller.
- **Unmasking**: *strict* replaces only placeholders that come back exactly as sent. *Robust* also accepts other brackets or none, any case, a space, hyphen or nothing instead of the underscore, and common type names (`[Person 1]`, `[PERSON1]`, `(PERSON_2)`, `PERSON_1`, `[NAME_1]`). Plain prose such as "Person 1" without brackets or underscore is left alone.
- **Model** (`maskrt/llm.py`): Qwen2.5-1.5B-Instruct as a Q4_K_M GGUF file, run by llama.cpp's `llama-server` on the CPU, one request at a time, greedy decoding (temperature 0, top-k 1, seed 0), at most 160 new tokens. Task: "Summarise the following message in two or three sentences. Write the summary in the language of the message." Two prompts: `plain` (only the task) and `instructed` (the task plus a paragraph that says to copy placeholders exactly). The input is the text masked by the `combined` detector, so leaked values reach the model as they would in use.

### Measures (`maskrt/metrics.py`, `maskrt/survival.py`)

- A labelled value **leaks** if any non-space character of it is not masked. **Leak rate** = leaked labelled values / all labelled values. Recall of a type = 1 − its leak rate.
- A masked span is **correct** if at least half of its non-space characters lie inside labelled values; otherwise it is **over-masking**. Precision = correct / all masked spans. Over-masking leaks nothing, but hides text the model may need.
- **95 % intervals**: percentile bootstrap over documents (2000 resamples, seed 0), because the values in one document are not independent.
- **Placeholders in answers**: every placeholder-like token in an answer is *exact* (as sent), *altered* (a changed form of one that was sent) or *invented* (not sent, including tokens such as `[HERR_Nguyen]`). An answer is *fully restored* when no placeholder-like token is left after unmasking.

## Results

Test set version `8f2a64384296` (first 12 digits of the SHA-256 of `data/documents.json`). The tables are printed by `python -m maskrt tables` from `results/detection.json` and `results/roundtrip.json`.

### Leakage

| Detector | Labelled values that leak | Leak rate (95 % interval) | Documents with a leak (95 % interval) | Over-masked spans | ms per document (median) |
|---|---|---|---|---|---|
| rules | 91 of 176 | 51.7 % (44.5 to 59.4 %) | 48 of 48 (100.0 to 100.0 %) | 3 of 88 | 0.14 |
| ner_multi | 105 of 176 | 59.7 % (53.7 to 65.5 %) | 45 of 48 (85.4 to 100.0 %) | 47 of 130 | 5.53 |
| ner_lang | 104 of 176 | 59.1 % (52.5 to 65.1 %) | 42 of 48 (77.1 to 95.8 %) | 31 of 125 | 10.41 |
| combined | 14 of 176 | 8.0 % (4.0 to 12.2 %) | 12 of 48 (12.5 to 37.5 %) | 65 of 222 | 16.95 |

### Recall per type (labelled values fully masked)

| Type | Labelled | rules | ner_multi | ner_lang | combined |
|---|---|---|---|---|---|
| PERSON | 91 | 0 (0.0 %) | 66 (72.5 %) | 66 (72.5 %) | 77 (84.6 %) |
| EMAIL | 17 | 17 (100.0 %) | 4 (23.5 %) | 2 (11.8 %) | 17 (100.0 %) |
| PHONE | 16 | 16 (100.0 %) | 0 (0.0 %) | 0 (0.0 %) | 16 (100.0 %) |
| IBAN | 7 | 7 (100.0 %) | 0 (0.0 %) | 1 (14.3 %) | 7 (100.0 %) |
| ADDRESS | 14 | 14 (100.0 %) | 1 (7.1 %) | 0 (0.0 %) | 14 (100.0 %) |
| DATE_OF_BIRTH | 13 | 13 (100.0 %) | 0 (0.0 %) | 1 (7.7 %) | 13 (100.0 %) |
| CUSTOMER_ID | 18 | 18 (100.0 %) | 0 (0.0 %) | 2 (11.1 %) | 18 (100.0 %) |

### Per language

| Language | Detector | Recall | Precision |
|---|---|---|---|
| de | rules | 40/86 (46.5 %) | 40/41 (97.6 %) |
| de | ner_multi | 37/86 (43.0 %) | 46/77 (59.7 %) |
| de | ner_lang | 37/86 (43.0 %) | 47/72 (65.3 %) |
| de | combined | 78/86 (90.7 %) | 74/119 (62.2 %) |
| en | rules | 45/90 (50.0 %) | 45/47 (95.7 %) |
| en | ner_multi | 34/90 (37.8 %) | 37/53 (69.8 %) |
| en | ner_lang | 35/90 (38.9 %) | 47/53 (88.7 %) |
| en | combined | 84/90 (93.3 %) | 83/103 (80.6 %) |

### Precision per masked type

| Detector | Type | Correct / masked | Precision |
|---|---|---|---|
| rules | EMAIL | 17/18 | 94.4 % |
| rules | PHONE | 16/18 | 88.9 % |
| rules | ADDRESS, CUSTOMER_ID, DATE_OF_BIRTH, IBAN | 52/52 | 100.0 % |
| ner_multi | PERSON | 67/96 | 69.8 % |
| ner_multi | LOCATION | 16/34 | 47.1 % |
| ner_lang | PERSON | 74/88 | 84.1 % |
| ner_lang | LOCATION | 20/37 | 54.1 % |
| combined | PERSON | 72/106 | 67.9 % |
| combined | LOCATION | 2/28 | 7.1 % |

(`python -m maskrt tables` prints every row.)

### Same person, same placeholder (combined)

16 labelled people are mentioned more than once in their document. Three got two placeholders: "Anna" after Anna Lehmann and Anna Petersen (`de-06`), "Sam" after Sam Keller and Sam Moretti (`en-05`), and "Doyle" (`en-20`, where the detector masked "Doyle v. Harbour Freight Ltd" as one name). One placeholder stands for two people: Joy Fisher and her father, Mr Fisher (`en-23`).

### The round trip through the model

48 documents, two prompts, 96 answers. Placeholder tokens counted over all answers:

| Prompt | Placeholder tokens in answers | Exact | Altered | Invented | Answers fully restored, strict unmasking | Answers fully restored, robust unmasking |
|---|---|---|---|---|---|---|
| plain | 142 | 135 (95.1 %) | 5 (3.5 %) | 2 (1.4 %) | 45 of 48 (93.8 %) | 47 of 48 (97.9 %) |
| instructed | 158 | 156 (98.7 %) | 0 (0.0 %) | 2 (1.3 %) | 46 of 48 (95.8 %) | 46 of 48 (95.8 %) |

- The altered forms were all brackets dropped: `PERSON_1`, `PERSON_2`, `PERSON_3` in one answer and `CUSTOMER_ID_1` in another. Robust unmasking restores them.
- The invented ones cannot be restored by any unmasking. In `en-18` the model repeated a sentence with `[PERSON_2]` and `[PHONE_2]`, which do not exist. With the instruction, it wrapped a leaked name into a placeholder of its own: `[HERR_Nguyen]` (`de-09`) and `[PERSON_2]` for the leaked neighbour "olu" (`en-18`).
- Of the 215 placeholders sent per prompt, 82 (plain) and 65 (instructed) do not appear in the answer. A summary may leave a person out, so this is not counted as an error.
- Leaked values come back: in 4 (plain) and 7 (instructed) answers the model repeated a value that the detector had missed.

**Speed.** Detection: 0.14 ms per document for the rules, 17 ms for all detectors together (median of five runs per document). Model: 96 answers in 146.7 s of wall time, 1.53 s per answer on average, 6039 new tokens. One laptop: AMD Ryzen 7 5800HS (8 cores, 16 threads), Windows 11, llama.cpp with its default thread count. One measurement, no interval.

## What fails, and why

- **Names that are also words, and names standing alone.** All 14 values that leak through the combined detector are names (`results/detection.json`, `leaks`): "Sommer", "Bauer", "Mark" and "Grace", each next to the same word in its ordinary sense; surnames alone ("Hoffmann", "Nguyen", "Petrović", "Schulte", "Achterberg"); first names alone ("Fatma"); lower-case names in chats ("max", "jess", "olu"); and one full name, "Isla McKenzie". The small spaCy models see little context in a two-line message.
- **The small NER models over-mask.** Words at the start of a line are taken for names: "Betreff", "Bitte", "Rückruf", "Hey", "Agenda". 65 of 222 masked spans of the combined detector are not personal data, 26 of 28 places are wrong. This is not free: in `de-14` "Betreff" and "Personalnummer" became `[PERSON_1]` and `[PERSON_3]`, the model treated them as people, and the restored answer says the sender is "informing Betreff". `web/` shows this document.
- **Linking mentions of one person is guesswork.** Subset matching links "Herr Koch" to "Martin Koch", but it cannot tell a father from a daughter with the same surname, and it gives up on an ambiguous first name.
- **The model ignores "in the language of the message".** In this run it wrote its summaries in English, also for the German texts. For the placeholders this hardly matters; for a product it would.
- **The model does not keep roles straight on its own.** Unmasking puts back the value that belongs to a number, but whether the model attached the right action to the right number is not checked automatically. In `de-04` (instructed) it calls `[PERSON_1]` the presenter, which is the over-masked heading, while the minutes say `[PERSON_2]` presented.

## Limits

- **Invented data, written by one person.** The rules and the test texts were written by the same person, so 100 % recall on IBANs, phone numbers and addresses says that the rules cover the formats used here, not every format. Real messages are longer, messier and contain formats not seen here.
- **Small set.** 176 labelled values in 48 documents; the intervals above show how wide that leaves the leak rate.
- **IBANs are matched by shape.** The test IBANs have wrong check digits on purpose, so the checksum test (`iban_checksum_ok`) is off. On real data it should be on.
- **`ner_lang` is told the language.** The test set gives it; a real system would have to detect it.
- **One small model, one task, one run.** Qwen2.5-1.5B-Instruct summarising in greedy mode. Larger models, other tasks (draft a reply, extract fields) or sampling will behave differently.
- **Speed** was measured once on one laptop.

## How to rerun

Python 3.12 and, for the page, Node 24.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt      # Linux/macOS: .venv/bin/pip
```

The models are files, not packages. They go into `models/` (not in git):

- spaCy models: the conda-forge packages `spacy-model-xx_ent_wiki_sm`, `spacy-model-de_core_news_sm`, `spacy-model-en_core_web_sm`, version 3.8.0 (noarch). Unpack each and copy its folder `<name>-3.8.0` (the one with `meta.json`) to `models/spacy/`. They are the same model packages spaCy publishes on GitHub and Hugging Face; conda-forge was used because those hosts did not answer from the machine of this run.
- Language model: `models/qwen2.5-1.5b-instruct-q4_K_M.gguf`, SHA-256 `183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4` (986048512 bytes). It is the model layer of `qwen2.5:1.5b-instruct` in the Ollama registry, fetched as `https://registry.ollama.ai/v2/library/qwen2.5/blobs/sha256:183715c4...`. Qwen's own GGUF on Hugging Face (`Qwen/Qwen2.5-1.5B-Instruct-GGUF`, file `qwen2.5-1.5b-instruct-q4_k_m.gguf`) should work the same; it is a different file and was not measured.
- llama.cpp: `llama-server` from conda-forge, `llama.cpp=12418=cpu_mkl_h4af3a8a_0`, e.g. `conda create -p .llama -c conda-forge llama.cpp=12418=cpu_mkl_h4af3a8a_0`. Or any `llama-server` on the PATH, or `MASKRT_LLAMA_SERVER=<path>`.

Then:

```
python -m maskrt check-data      # the test set matches data/MANIFEST.sha256
python -m maskrt detect          # -> results/detection.json   (seconds)
python -m maskrt model           # -> results/answers.json     (about 3 minutes here)
python -m maskrt analyse         # -> results/roundtrip.json
python -m maskrt export          # -> results/viewer.json
python -m maskrt tables          # the tables above
python -m maskrt all             # all of it
```

`python -m maskrt build-data` rebuilds `data/documents.json` and the manifest after a change to `data/annotated.txt`.

The page: `cd web && npm ci && npm run dev`. It shows one document at a time: original with the hand labels (leaked ones in red), masked text, model answer (exact, altered and invented placeholders) and restored answer.

## What is tested

`pytest` (33 tests) and `ruff check .`; GitHub Actions also checks the manifest, runs `python -m maskrt smoke` (rules only, no model, a made-up answer through unmasking) and type-checks and builds the page.

- Masking (`tests/test_masking.py`): same value, same placeholder; numbering per type; surname linked to the full name; ambiguous first name not linked; phone numbers with different spacing; merging of overlaps; offsets; strict and robust unmasking, including invented placeholders and prose that must stay; a round trip without a model gives back the original.
- Metrics (`tests/test_metrics.py`): protected, partly masked and over-masked spans; the half-inside rule; summary per type and language; the bootstrap interval contains the estimate and repeats with the same seed; split and merged people.
- Survival (`tests/test_survival.py`): exact, altered, invented and dropped placeholders; leaked values repeated by the model; counts before and after robust unmasking.
- Rules and data (`tests/test_rules_and_data.py`): every rule on German and English formats, numbers that must not match, the birth-word rule, the IBAN checksum, the line-break cut, the annotation parser, the manifest, and that no test IBAN validates and every e-mail uses a reserved domain.

Not tested: the spaCy models and the language model themselves (they are measured, not unit-tested), the page in a browser, other platforms than Windows for the model run.

## Files

| File | What it does |
|---|---|
| `data/annotated.txt`, `data/README.md` | The hand-labelled test set and its labelling rules. |
| `maskrt/dataset.py` | Parses the labels into offsets, builds `documents.json`, checks the manifest. |
| `maskrt/rules.py`, `maskrt/ner.py` | The detectors. |
| `maskrt/spans.py`, `maskrt/masking.py` | Merging, placeholders, strict and robust unmasking. |
| `maskrt/metrics.py`, `maskrt/survival.py` | Leakage, precision, recall, bootstrap; placeholder survival. |
| `maskrt/llm.py` | Starts `llama-server` and sends the prompts. |
| `maskrt/pipeline.py`, `maskrt/__main__.py`, `maskrt/report.py` | The steps, the command line, the tables. |
| `results/` | Every number in this file. |
| `web/` | The page (Vite, TypeScript). |

## Licence

Code and test set: MIT, see [`LICENSE`](LICENSE). Models used, as stated in their own metadata: spaCy `xx_ent_wiki_sm`, `de_core_news_sm`, `en_core_web_sm` 3.8.0, MIT (`meta.json`; their training data have their own licences, listed there); Qwen2.5-1.5B-Instruct, Apache-2.0. The models are not part of this repository.
