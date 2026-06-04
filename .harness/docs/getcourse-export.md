# GetCourse Export Sample

Source files inspected:

`C:\Users\circlealgorythm\Downloads\Telegram Desktop\Для мешка выгрузка.csv`

`C:\Users\circlealgorythm\Desktop\user_export_with_group_id_date_2026-05-21_11-39-17.xlsx`

`C:\Users\circlealgorythm\Pictures\Ксюша\Проекты\user_export_with_group_id_date_2026-05-21_11-39-17.xlsx`

Observed CSV format:

- Encoding: `cp1251`.
- Delimiter: tab (`\t`), despite `.csv` extension.
- Rows: header only in the provided sample.
- Columns: 39.

Observed XLSX format:

- Sheet: `Лист1`.
- Rows: 2.
- Columns: 39 in the earlier sample; 27 in the later user-provided sample.
- Header row can differ by export settings.
- Row 2 contains one real/anonymizable user row.
- The earlier 39-column sample has headerless custom columns 14-21.
- The later 27-column sample has headerless custom columns 12-19.
- Headerless custom columns contain actual custom field values such as `Да` or empty values.
- No hidden columns and no merged cells were observed.

Observed columns:

Earlier 39-column export:

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

Later 27-column export:

1. `Email`
2. `Тип регистрации`
3. `Создан`
4. `Последняя активность`
5. `Имя`
6. `Фамилия`
7. `Телефон`
8. `Дата рождения`
9. `Возраст`
10. `Страна`
11. `Город`
12. blank/custom field column
13. blank/custom field column
14. blank/custom field column
15. blank/custom field column
16. blank/custom field column
17. blank/custom field column
18. blank/custom field column
19. blank/custom field column
20. `Откуда пришел`
21. `utm_source`
22. `utm_medium`
23. `utm_campaign`
24. `utm_term`
25. `utm_content`
26. `utm_group`
27. `VK-ID`

Later 27-column sample row highlights:

- `Имя`: `Сергей тест`
- `Фамилия`: `Gurbin`
- `Откуда пришел`: `mamba.ru`
- Yandex attribution is in regular `utm_*`: `Yandex`, `cpc`, `116900226`, `шаманизм`, `16736567277`
- `VK-ID`: present
- Headerless custom columns contain the pattern `Да`, empty, `Да`, empty, `Да`, `Да`, `Да`, empty.

Custom field / consent notes:

- The blank-looking columns in the export are not safe to drop.
- In GetCourse UI these columns correspond to additional user fields (`Custom Field ...`).
- The provided screenshots show these custom fields can represent checkbox consents for privacy policy / offer agreement.
- In the sample XLSX row, some of these custom field columns contain `Да`, meaning the checkbox was likely enabled for that user.
- Because the export does not provide human-readable custom field names in the header, imports should preserve these columns by blank-column order and map that order to the known GetCourse custom field IDs. Do not rely on one fixed absolute column number because exports can be 39-column or 27-column depending on selected fields.
- If GetCourse can export custom field IDs/names separately, store that mapping in the system and use it during import.

Import design notes:

- Parser must support `cp1251` input and tab-separated files.
- Parser must support `.xlsx` input.
- Import UI should not trust the `.csv` extension as comma-separated.
- Blank/headerless columns must not be ignored automatically because they may be GetCourse custom fields.
- Headerless consent columns are mapped by blank-column order to the known eight checkbox fields:
  `custom_10558670`, `custom_10575005`, `custom_10616540`, `custom_10661024`,
  `custom_10682753`, `custom_10682754`, `custom_10683365`, `custom_11344348`.
- Deduplication candidates from this export: `id`, `Email`, `Телефон`, `VK-ID`.
- UTM data appears in two groups: `gc_system_user_utm_*` and manual/current `utm_*`.
- Inbox should use only manual/current `utm_*` values for advertising attribution, especially Yandex Direct data. `gc_system_user_utm_*` values are GetCourse-owned system fields, are often empty, and should remain only in raw row data rather than operational `lead_utm` snapshots.
- Partner and manager fields should be stored as external/context metadata unless they become first-class entities later.
- Raw import rows should be stored as JSON for traceability, including unknown/custom/headerless fields.
- Suggested custom field storage: `lead_custom_fields` with `source`, `field_key`, `field_label`, `field_position`, `value`, and optional normalized boolean value.
