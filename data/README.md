# Test set

48 short business texts, 24 in German and 24 in English: support e-mails, HR notes, invoices, meeting notes, chat messages, contract extracts, delivery notices, a legal letter, CRM notes. 176 spans of personal data are labelled by hand.

- `annotated.txt` is the source. It is written and labelled by hand: `[[TYPE:value]]`, or `[[TYPE#key:value]]` when several mentions belong to one person.
- `documents.json` is built from it (`python -m maskrt build-data`): the plain text of every document and each label with its character offsets.
- `MANIFEST.sha256` holds the SHA-256 of both files. Every run checks it and writes the first 12 digits of the `documents.json` hash into its results as the version of the set.

## Everything is invented

No text, name, address or number belongs to a real person. Any match with a real person, street or line is chance.

- **IBANs** have deliberately wrong check digits: none of them passes the ISO 13616 check (a test asserts this). The German ones use the made-up bank code `9999...`, the British ones the made-up bank code `ZZTB`.
- **E-mail addresses** use the reserved domains `example.com`, `example.org`, `example.net` or names ending in `.example`.
- **Phone numbers**: the British ones come from the ranges Ofcom keeps for drama (`07700 900xxx`, `020 7946 0xxx`, `01632 960xxx`), the American ones from `555-01xx`. In the German ones the part after the area or network code starts with 0, to make a match with a real line unlikely.
- **Streets** are invented names with real postcodes and cities.

## Labelling rules

| Type | What is labelled |
|---|---|
| `PERSON` | Names of people: full names, first names alone, surnames alone, lower-case names in chats. Titles and salutations (Herr, Frau, Dr., Mr, Ms, Mrs) are not part of the span. A genitive "s" is not part of the span (`[[PERSON:Hoffmann]]s`). A name inside a compound word is labelled alone (`[[PERSON:Hoffmann]]-Präsentation`). |
| `EMAIL` | Personal e-mail addresses. A function mailbox (`buchhaltung@shop.example`) is not labelled. |
| `PHONE` | Phone numbers of people. A company hotline is not labelled. |
| `IBAN` | Account numbers in IBAN form, with or without spaces. |
| `ADDRESS` | A postal address with street and house number, with postcode and city when they follow. A city alone is not labelled. |
| `DATE_OF_BIRTH` | Dates of birth. Other dates (meetings, deadlines, invoices) are not labelled. |
| `CUSTOMER_ID` | Customer, employee, member, policy and contract numbers that belong to a person. Order, invoice, ticket, tracking, article and court file numbers are not labelled. |

Not labelled at all: company names, even when they contain a surname ("Schreinerei Albers GmbH", "Patel Logistics Ltd", "Lang & Söhne"); cities and buildings on their own; amounts, quantities, versions, norms, room numbers.

## Hard cases on purpose

- Names that are also words, next to the word: Koch / der Koch, Sommer / im Sommer, Klein / zu klein, Bauer / der Bauer, Will / will, Mark / mark, Grace / grace period, Hunter / hunter green, Fuchs / Fuchsbau.
- Two people with the same first name, then the first name alone: Anna Lehmann and Anna Petersen, then "Anna aus dem Vertrieb"; Sam Keller and Sam Moretti, then "Sam from finance".
- Two people with the same surname: Joy Fisher and her father, Mr Fisher.
- A name inside an e-mail address (`moritz.engelhardt82@example.org`), inside a compound word, in the genitive, in lower case.
- Numbers that are not personal data: amounts, a 16-digit tracking number, ticket ranges, article numbers, ISO 27001, versions, a company hotline.
