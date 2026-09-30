# Google Health notification bodies

Raw request bodies for `POST /api/googleHealth/notifications`
(`tests/test_google_health_notifications.py`).

Source: <https://developers.google.com/health/webhooks>, fetched 2026-09-30 (page footer
"Last updated 2026-09-24 UTC"). The first four files are the page's JSON bodies copied
verbatim (the HTTP request lines above each example are dropped).

| File | Origin | Dates the receiver derives |
|------|--------|----------------------------|
| `upsert_steps.json` | "Upsert (time-series data)": all three interval forms | `2026-03-07` (from `civilDateTimeInterval`) |
| `delete_steps_timeseries.json` | "Delete (time-series data)": a JSON array; `physicalTimeInterval` and `civilIso8601TimeInterval` only | `2026-08-12` (from `civilIso8601TimeInterval`) |
| `delete_sleep_record_id.json` | "Delete (identifiable data)": `dataType: sleep`, 22:00 to 06:00, `recordId` | `2026-08-12`, `2026-08-13` |
| `full_day_steps.json` | "Time intervals" full-day example: `civilDateTimeInterval` ending 00:00 the next day, no `physicalTimeInterval` | `2026-07-14` only |
| `physical_only_steps.json` | Derived: `upsert_steps.json` with both civil forms removed | `2026-03-07`..`2026-03-09` (UTC `2026-03-08`, widened one day each side) |
| `batch_mixed.json` | Derived: a JSON array of `upsert_steps.json`, `full_day_steps.json` (with `healthUserId` set to `health-user-id`) and `delete_sleep_record_id.json` | two groups: (`steps`, `UPSERT`) `2026-03-07`, `2026-07-14`; (`sleep`, `DELETE`) `2026-08-12`, `2026-08-13` |

The page's "Aggregation of updates" section says batches arrive "as a JSON array containing
multiple notification objects" (at most 99 per batch) and links a "Batch (multiple users and
data types)" example that the 2026-09-30 page does not contain. `batch_mixed.json` is
therefore assembled from the page's own single-notification examples.
