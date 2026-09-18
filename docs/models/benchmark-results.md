# Mesh Benchmark Results

No production GPU benchmarks have been run in this restart. The current checked-in results are deterministic mock-pipeline checks.

| Fixture | Adapter stack | Expected behavior | Current status |
|---|---|---|---|
| Solo dance | mock-yolo + mock-bytetrack + mock-mhr | One person, non-empty mesh asset, beats/difficulty/path trails | Covered by contracts fixture and API tests |
| Two-person crossing | mock-yolo + mock-bytetrack + mock-mhr | Stable `person-alpha` / `person-beta` IDs through crossing | Covered by API integration test |
| Group / partial failure | mock-yolo + mock-bytetrack + mock-mhr | One failed mesh track is returned as partial result | Covered by contracts fixture and API tests |
| No people | mock-yolo + mock-bytetrack + mock-mhr | Job fails with clear no-people error | Covered by API test |
