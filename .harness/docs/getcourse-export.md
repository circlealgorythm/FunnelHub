# GetCourse Export Sample

Source files inspected:

`C:\Users\circlealgorythm\Downloads\Telegram Desktop\Для мешка выгрузка.csv`

`C:\Users\circlealgorythm\Desktop\user_export_with_group_id_date_2026-05-21_11-39-17.xlsx`

Observed CSV format:

- Encoding: `cp1251`.
- Delimiter: tab (`\t`), despite `.csv` extension.
- Rows: header only in the provided sample.
- Columns: 39.

Observed XLSX format:

- Sheet: `Лист1`.
- Rows: 2.
- Columns: 39.
- Header row matches the CSV export.
- Row 2 contains one real/anonymizable user row.
- Columns 14-21 have blank-looking headers represented as `' '`, but contain actual custom field values such as `Да` or empty values.
- No hidden columns and no merged cells were observed.

Observed columns:

1. `id`
2. `Email`
3. `Тип регистрации`
4. `Создан`
5. `Последняя активность`
6. `Имя`
7. `Фамилия`
8. `Телефон`
9. `Дата рождения`
10. `Возраст`
11. `Страна`
12. `Город`
13. `От партнера`
14. blank/custom field column
15. blank/custom field column
16. blank/custom field column
17. blank/custom field column
18. blank/custom field column
19. blank/custom field column
20. blank/custom field column
21. blank/custom field column
22. `gc_system_user_utm_source`
23. `gc_system_user_utm_medium`
24. `gc_system_user_utm_campaign`
25. `gc_system_user_utm_term`
26. `gc_system_user_utm_content`
27. `Откуда пришел`
28. `utm_source`
29. `utm_medium`
30. `utm_campaign`
31. `utm_term`
32. `utm_content`
33. `utm_group`
34. `ID партнера`
35. `Email партнера`
36. `ФИО партнера`
37. `ФИО менеджера`
38. `VK-ID`
39. `id групп пользователя/дата добавления`

Custom field / consent notes:

- The blank-looking columns in the export are not safe to drop.
- In GetCourse UI these columns correspond to additional user fields (`Custom Field ...`).
- The provided screenshots show these custom fields can represent checkbox consents for privacy policy / offer agreement.
- In the sample XLSX row, some of these custom field columns contain `Да`, meaning the checkbox was likely enabled for that user.
- Because the export does not provide human-readable custom field names in the header, imports should preserve these columns by position and allow mapping them manually to semantic fields such as privacy consent or offer consent.
- If GetCourse can export custom field IDs/names separately, store that mapping in the system and use it during import.

Import design notes:

- Parser must support `cp1251` input and tab-separated files.
- Parser must support `.xlsx` input.
- Import UI should not trust the `.csv` extension as comma-separated.
- Blank/headerless columns must not be ignored automatically because they may be GetCourse custom fields.
- Deduplication candidates from this export: `id`, `Email`, `Телефон`, `VK-ID`.
- UTM data appears in two groups: `gc_system_user_utm_*` and manual/current `utm_*`.
- Partner and manager fields should be stored as external/context metadata unless they become first-class entities later.
- Raw import rows should be stored as JSON for traceability, including unknown/custom/headerless fields.
- Suggested custom field storage: `lead_custom_fields` with `source`, `field_key`, `field_label`, `field_position`, `value`, and optional normalized boolean value.
