---
name: cibc-fact-finder
description: Extracts client financial data from uploaded discovery documents, advisor meeting notes, WPG exports, or prior fact finders, then populates Chris Mylonas's CIBC Private Wealth Consultation Questionnaire (Fact Finder) PDF using a pre-built 325-field semantic map. Use whenever asked to fill, populate, complete, or process a "fact finder," "CIBC questionnaire," "consultation questionnaire," or client discovery document — including when the user just uploads a document and says something like "fill this out," "process this client," or "run the fact finder."
---

# CIBC Fact Finder Auto-Fill

**Advisor:** Chris Mylonas — CIBC Financial Planning and Advice
**Template:** `assets/CIBC_FactFinder_Blank_Template.pdf` (fillable form, 325 fields across 7 pages)
**Field Map:** `references/CIBC_FactFinder_FieldID_Map.json` (all 325 field IDs pre-mapped to semantic meaning, page, and coordinates)
**Quick Reference:** `references/quick_reference.md` (common field lookups, planning gap checklist, notes-page template, known quirks)
**PDF scripts:** this skill relies on `fill_fillable_fields.py` and `convert_pdf_to_images.py` from the public `pdf` skill. If those aren't available in the current environment, read `/mnt/skills/public/pdf/SKILL.md` first.

-----

## ⚠️ Bundled files are read-only — read first, every session

This skill bundles three permanent source files that must never be modified or overwritten:

| File | Purpose |
|------|---------|
| `assets/CIBC_FactFinder_Blank_Template.pdf` | Blank fillable template — the master source |
| `references/CIBC_FactFinder_FieldID_Map.json` | Field ID map — never regenerate |
| `references/quick_reference.md` | Lookup tables, checklist, and edge-case notes |

**Rules — enforce every time this skill runs:**
- Always read the template from this skill's own `assets/` folder (locate the skill's mounted directory rather than assuming a fixed path — it varies by surface: Claude Code uses `~/.claude/skills/cibc-fact-finder/`, claude.ai/Cowork mount it wherever the skill appears in your available-skills listing).
- Never write any file back into the skill's own folder, even a "corrected" version.
- All filled PDFs, verification images, and intermediates go to your working directory (e.g. `/home/claude/`) or the final output directory (e.g. `/mnt/user-data/outputs/`) only.

-----

## How to trigger this workflow

Say any of the following (or just upload a document and ask):

- "Fill the fact finder for [Client Name]"
- "Populate the CIBC questionnaire from this document"
- "Process this discovery questionnaire"

Upload one or more source documents alongside the request.

-----

## Step-by-Step Execution

### Step 1 — Verify the template is intact

```bash
file <skill_dir>/assets/CIBC_FactFinder_Blank_Template.pdf
cd /mnt/skills/public/pdf
python scripts/check_fillable_fields.py <skill_dir>/assets/CIBC_FactFinder_Blank_Template.pdf
```

Expected: `PDF document, version 1.6` and `This PDF has fillable form fields`. Then confirm field count and known defaults:

```python
from pypdf import PdfReader
r = PdfReader('<skill_dir>/assets/CIBC_FactFinder_Blank_Template.pdf')
fields = r.get_fields()
print(len(fields))              # Must be 325
print(fields['Text4.0']['/V'])  # Must be 'Chris Mylonas'
```

If any check fails — **stop immediately and alert Chris.** Do not attempt to fill the form or improvise an alternative approach.

-----

### Step 2 — Read the source document(s)

Accept any combination of: CIBC Discovery Questionnaire, advisor meeting notes (PDF or text/email), WPG/financial planning file export, a prior fact finder (partially filled), or any other client data document. Extract **all** data points — don't skip fields just because they seem minor.

-----

### Step 3 — Map extracted data to field IDs

Use `references/CIBC_FactFinder_FieldID_Map.json` to look up the correct `field_id` for each data point — it contains every field's ID, semantic meaning, page number, and coordinates. **Do not re-inspect the PDF.**

For the most commonly populated fields, `references/quick_reference.md` has a condensed semantic-name → field_id table so you don't need to search the full JSON for routine fields. For anything not in that table (business details, insurance rows, asset section rows beyond row 1, etc.), look it up in the full JSON.

-----

### Step 4 — Build field_values.json

Format:

```json
[
  {"field_id": "Text4.0", "description": "Client name on cover", "page": 1, "value": "Jane Smith & John Smith"},
  {"field_id": "Check Box54.1", "description": "Married checkbox", "page": 3, "value": "/Yes"}
]
```

**Critical rules:**
- Checkbox values MUST be `/Yes` (checked) or `/Off` (unchecked) — never `true`/`false` or `Yes`/`No`
- Include `page` matching the field_id map
- Leave fields blank (`""`) if data isn't available — don't omit the field entirely
- Date format: `DD/MM/YYYY`
- Dollar amounts: include `$` and comma formatting (e.g. `$1,250,000`)
- Family member rows: use rows 1–5 for numbered fields, then `6.0` and `6.1` for rows 6 and 7
- Goals rows: same pattern — 1–5, then `6.0` and `6.1`

**⚠️ Field name collision on page 3 — MUST follow this exact ordering, every time**, or values will bleed into the wrong rows:

1. All family member rows (`OF RESIDENCE 1`–`5`, `1`, `1_2`, `DDMMYYYY 1`, etc.)
2. All goal rows (`GOAL 1`–`5`, `TIME HORIZON 1`–`5`, etc.)
3. **Explicit empty-string clears for all `6.x` bleedthrough fields** (full list in `references/quick_reference.md`)
4. **All marital status checkboxes (`Check Box54.x`) placed LAST**

If you skip step 3 or reorder step 4 before it, family/goal row 6–7 data will silently overwrite or duplicate into the wrong cells.

-----

### Step 5 — Fill the PDF

```bash
cd /mnt/skills/public/pdf
python scripts/fill_fillable_fields.py \
  <skill_dir>/assets/CIBC_FactFinder_Blank_Template.pdf \
  /home/claude/field_values.json \
  /home/claude/[ClientLastName]_FactFinder_Filled.pdf
```

⚠️ The input is always the bundled blank template. Never use any other source path. If errors are reported, fix the offending field values (usually checkbox format issues) and re-run.

-----

### Step 6 — Verify output

```bash
mkdir -p /home/claude/verify
cd /mnt/skills/public/pdf
python scripts/convert_pdf_to_images.py \
  /home/claude/[ClientLastName]_FactFinder_Filled.pdf \
  /home/claude/verify/
```

Visually inspect all page images to confirm data landed in the correct fields and no phantom values appear. Then copy to outputs:

```bash
cp /home/claude/[ClientLastName]_FactFinder_Filled.pdf \
   /mnt/user-data/outputs/[ClientLastName]_CIBC_FactFinder_Filled.pdf
```

⚠️ **Never copy any file back into the skill's own folder.**

-----

### Step 7 — Output to advisor

Present the filled PDF, then provide:
1. Summary of what was populated
2. List of fields left blank due to missing source data
3. A planning-gaps advisory note — use the checklist and notes-page template in `references/quick_reference.md`

-----

## Known critical quirks (see `references/quick_reference.md` for the full list)

| Issue | Solution |
|-------|----------|
| Checkbox values rejected | Must be exactly `/Yes` or `/Off` (with leading slash) |
| Field name collision (page 3) | Fields `1`, `2` etc. bleed into `6.1` rows and marital checkboxes — follow Step 4 ordering exactly |
| Total Assets (single value) | Fill BOTH `Text56.18.0.0` AND `Text56.18.0.1.0` |
| Template pre-filled defaults | `Text4.0`=`Chris Mylonas`, Citizenship fields=`Ontario`, total rows=`0`, `Text57.0`=`MORTGAGE 1` — these are factory defaults, not errors |
