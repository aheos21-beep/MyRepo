# CIBC Fact Finder — Quick Reference

Supporting reference for `SKILL.md`. Read this during Step 3 (field lookups), Step 4 (collision clears), and Step 7 (planning gaps + notes page).

-----

## Semantic Name → field_id (most commonly populated fields)

| Semantic Name | field_id |
|---|---|
| cover_client_name | Text4.0 |
| cover_date | Text4.1 |
| client_name | Text52.0 |
| client_dob | Date of birth |
| client_citizenship | Citizenship |
| client_country_of_residence | Country of residence for income tax purposes |
| client_occupation | Occupation |
| client_employer | Employer |
| client_employment_income | Employment income |
| client_other_income | Other income sources |
| spouse_name | Name |
| spouse_dob | Date of birth_2 |
| spouse_citizenship | Citizenship_2 |
| spouse_occupation | Occupation_2 |
| spouse_employer | Employer_2 |
| spouse_employment_income | Employment income_2 |
| spouse_other_income | Other income sources_2 |
| expense_monthly_checkbox | Check Box53.0 |
| expense_annual_checkbox | Check Box53.1 |
| lifestyle_expenses_amount | Monthly or  Annual aftertax expenses |
| marital_status_single | Check Box54.0 |
| marital_status_married | Check Box54.1 |
| marital_status_commonlaw | Check Box54.2 |
| marital_status_separated | Check Box54.3 |
| marital_status_divorced | Check Box54.4 |
| marital_status_widowed | Check Box54.5 |
| date_of_marriage | Married    Commonlaw  Separated |
| family_N_name_province | OF RESIDENCE N |
| family_N_relationship | N (just the number) |
| family_N_marital_status | N_2 |
| family_N_dob | DDMMYYYY N |
| goal_N_description | GOAL N |
| goal_N_time_horizon | TIME HORIZON N |
| goal_N_considerations | CONSIDERATIONS N |
| goal_N_priority | PRIORITY N |
| bank_row1_description | Text55.0 |
| bank_row1_joint_spouse | Text56.0.2 |
| bank_total_joint_spouse | Text56.2.2 |
| nonreg_row1_description | Text55.2 |
| nonreg_row1_joint_spouse | Text56.3.2 |
| nonreg_total_self | Text56.5.0 |
| nonreg_total_spouse | Text56.5.1 |
| nonreg_total_joint_spouse | Text56.5.2 |
| rrsp_row1_description | Text55.4 |
| rrsp_row1_spouse | Text56.6.1 |
| rrsp_total_spouse | Text56.8.1 |
| pension_row1_description | Text55.6 |
| pension_row1_self | Text56.9.0 |
| pension_total_self | Text56.11.0 |
| pension_total_spouse | Text56.11.1 |
| realestate_row1_description | Text55.8 |
| personalprop_row1_description | Text55.10 |
| total_assets_by_ownership_self | Text56.17.0 |
| total_assets_by_ownership_spouse | Text56.17.1 |
| total_assets_by_ownership_joint_spouse | Text56.17.2 |
| total_assets_amount | Text56.18.0.0 |
| total_assets_grand_total | Text56.18.0.1.0 |
| liability_row1_description | Text57.0 |
| total_liabilities_grand | Text56.18.0.1.1 |
| business_row1_name | Text58.5.0 |
| business_row1_fmv | Text58.5.1 |
| business_total_fmv | Text57.4 |
| total_family_net_worth | Text57.5.0 |
| biz_structure_sole_prop | Check Box63.0 |
| biz_structure_partnership | Check Box63.1 |
| biz_structure_corp_private | Check Box63.2 |
| business_address | Text62.0 |
| business_nature | Text62.1 |
| business_place_of_incorp | Text59.3 |
| business_notes_line1 | Text59.4.0 |
| indiv_ins_row1_issuer | Text60.0 |
| indiv_ins_row1_self | Text61.0.0 |
| indiv_ins_row1_spouse | Text61.0.1 |
| indiv_ins_row1_beneficiary | Text61.0.2.1 |
| group_ins_row1_issuer | Text60.3 |
| group_ins_row1_self | Text61.5.0 |
| group_ins_row1_spouse | Text61.5.1 |
| group_ins_row1_beneficiary | Text61.5.2 |
| notes_general | Text51.0 |

For all 325 field IDs (every row, every section, full coordinates), refer to `CIBC_FactFinder_FieldID_Map.json` in this same folder.

-----

## Page 3 collision — explicit clears required

The family relationship fields (`1`, `2`, `3`…) share internal names with other fields in the PDF. Build `field_values.json` in the exact order described in `SKILL.md` Step 4, and include these explicit empty-string clears for all `6.x` bleedthrough fields **after** family/goal data and **before** the marital checkboxes:

```json
{"field_id": "OF RESIDENCE 6.0", "page": 3, "value": ""},
{"field_id": "6.0",              "page": 3, "value": ""},
{"field_id": "6_2.0",            "page": 3, "value": ""},
{"field_id": "DDMMYYYY 6.0",     "page": 3, "value": ""},
{"field_id": "OF RESIDENCE 6.1", "page": 3, "value": ""},
{"field_id": "6.1",              "page": 3, "value": ""},
{"field_id": "6_2.1",            "page": 3, "value": ""},
{"field_id": "DDMMYYYY 6.1",     "page": 3, "value": ""},
{"field_id": "GOAL 6.1",         "page": 3, "value": ""},
{"field_id": "TIME HORIZON 6.1", "page": 3, "value": ""},
{"field_id": "CONSIDERATIONS 6.1","page": 3, "value": ""},
{"field_id": "PRIORITY 6.1",     "page": 3, "value": ""}
```

Then place all `Check Box54.x` entries **after** the clears.

-----

## Notes Page Content Standard

The `Text51.0` (`notes_general`) field on page 6 should always contain:

```
PLANNING NOTES - [Client Name] | Prepared by Chris Mylonas, CIBC FP&A | Date: DD/MM/YYYY

ESTATE DOCUMENTS:
- Wills: [status, date last updated]
- Executors: [names]
- Alternate Executors: [names or "Not specified"]
- POA for Financial Assets: [status]
- POA for Care: [status]
- Estate beneficiaries: [names or "Not specified"]
- Secondary Will (Ontario): [status]

KEY ASSETS:
[bullet list of all major asset items with FMV]

INCOME SOURCES:
[bullet list per client: salary, pension, LIF, CPP, OAS, rental, etc.]

PLANNING GAPS (ACTION REQUIRED):
[numbered list — see Planning Gap Checklist below]

RELATIONSHIP MANAGERS: [names if known]
```

-----

## Planning Gap Checklist

Check every source document for these items and flag any that are missing or unconfirmed:

| # | Item | Flag if… |
|---|---|---|
| 1 | Will in place | Not confirmed or >5 years old |
| 2 | POA for Property | Not confirmed |
| 3 | POA for Personal Care | Not confirmed |
| 4 | Life insurance | No policy on file |
| 5 | Disability insurance | No policy on file (if pre-retirement) |
| 6 | Critical illness insurance | No policy on file |
| 7 | RRSP contribution maximized | Unused room >$0 and still working |
| 8 | TFSA contribution maximized | Unused TFSA room available |
| 9 | Beneficiary designations current | Not confirmed or not named |
| 10 | CPP/OAS amounts and start dates | Not provided |
| 11 | Annual lifestyle expenses | Not provided |
| 12 | Anticipated inheritance | Mentioned but not documented |
| 13 | Business succession plan | Business interest present but no plan |
| 14 | Date of marriage | Not recorded |
| 15 | Alternate executors | Not named |
| 16 | Estate beneficiaries | Not specified |
| 17 | Secondary Will (Ontario clients) | Not confirmed |
| 18 | OAS clawback risk | Income near or above ~$90K threshold |
| 19 | Investment of large cash balances | Matured GICs or cash sitting idle |
| 20 | Concentration risk | Single stock/sector >20% of portfolio |

-----

## Known Quirks & Edge Cases (full list)

| Issue | Solution |
|---|---|
| Checkbox values rejected | Must be exactly `/Yes` or `/Off` (with leading slash) |
| Checkboxes appear unchecked in preview | Values are stored correctly in the PDF — will render properly in Adobe Acrobat and when printed |
| Field name collision (page 3) | Fields `1`, `2` etc. bleed into `6.1` rows and marital checkboxes — follow Step 4 ordering exactly |
| Family member rows 6 and 7 | Use field suffix `6.0` and `6.1`, not `6` and `7` |
| Goal rows 6 and 7 | Same as above — suffix `6.0` and `6.1` |
| Total Assets by Ownership (dark row) | `Text56.17.0`–`3`; separate from Total Assets line |
| Total Assets (single value) | Fill BOTH `Text56.18.0.0` AND `Text56.18.0.1.0` |
| Total Liabilities | `Text56.18.0.1.1` on page 5 |
| Business Total FMV label | `Text57.4` displays in the Name column — this is correct |
| Total Family Net Worth | `Text57.5.0` — appears below Total FMV row |
| Pension section | Use annual income amounts in description (e.g. "$34,800/yr") since capital value may not be available |
| Notes field (`Text51.0`) | Accepts long multi-line text; use `\n` for line breaks in the JSON value |
| Page 5 `Text59.1` / `Text59.2` | These are the "Private ___" and "Public ___" text fields next to the Corp checkbox |
| Template pre-filled defaults | `Text4.0`=`Chris Mylonas`, Citizenship fields=`Ontario`, total rows=`0`, `Text57.0`=`MORTGAGE 1` — these are factory defaults, not errors |

-----

## Asset Section → Field ID Quick Reference (Page 4)

Each asset section follows the same pattern:
- Row 1 description: `Text55.X`
- Row 1 Self/Spouse/Joint/Other: `Text56.X.0` / `.1` / `.2` / `.3`
- Row 2–4 descriptions and values: nested suffixes (see `CIBC_FactFinder_FieldID_Map.json`)
- Section total: `Text56.Y.0` through `.3`

| Section | Description fields | Total fields |
|---|---|---|
| Bank Accounts | Text55.0, Text55.1.x | Text56.2.0–3 |
| Non-Reg/TFSAs | Text55.2, Text55.3.x | Text56.5.0–3 |
| RRSPs/RRIFs | Text55.4, Text55.5.x | Text56.8.0–3 |
| Pension/Annuities | Text55.6, Text55.7.x | Text56.11.0–3 |
| Real Estate | Text55.8, Text55.9.x | Text56.14.0–3 |
| Personal Property | Text55.10, Text55.11.x | (no separate total row; goes to Total Assets by Ownership) |
