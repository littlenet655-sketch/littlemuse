# LittleNet Full Dataset Validation — 2026-09-08

Validated source bundles (dataset bytes are **not** committed to GitHub):

- `LittleNet_Dataset_Part1_of_2.zip`
- `LittleNet_Dataset_Part2_of_2.zip`

## Combined source inventory

- Master CSV copies: **2**, byte-identical
- Master CSV SHA-256: `1ecb3938b271218e0481158b6939ae9df52083cc4c7e80724667c5db0c6cf9df`
- Master CSV rows: **206**
- Master CSV columns: **24**
- Media files across both bundles: **206**
- Missing CSV-referenced media: **0**
- Extra media not represented in CSV: **0**
- Same logical path duplicated across Part 1 and Part 2: **0**
- File-size mismatches against CSV: **0**

### Archive/category counts

- `family.zip`: **74 / 74**
- `Member3Animals.zip`: **58 / 58**
- `Member3Crafts&Hobbies.zip`: **26 / 26**
- `Member3Gardening.zip`: **21 / 21**
- `Member3Cooking.zip`: **15 / 15**
- `18+images.zip`: **12 / 12**

### Dataset labels

- `ALLOWED`: **194**
- `BLOCKED`: **12**
- Videos: **127**
- Images: **79**
- Reels: **122**
- Non-reels: **84**

## Part 2 media validation

Part 2 contains exactly **110** media files:

- Family: **74**
- Gardening: **21**
- Cooking: **15**

Checks performed against the master CSV:

- File sizes: **110/110 pass**
- Image/video dimensions: **110/110 pass**
- Video durations: **all Part 2 videos pass** (within validation tolerance)
- Unreadable/corrupt image/video payloads: **0**

## Full-dataset blocking finding — one duplicate payload

A SHA-256 scan across all 206 media rows found **one duplicate byte payload**:

- CSV row `34` / `Member3Animals.zip` / `fun-animal-facts-for-kids.jpg`
  - title: `Fun Animal Facts: Nature's Record Breakers`
  - category: Nature / Animals
- CSV row `120` / `Member3Gardening.zip` / `fun-animal-facts-for-kids.jpg`
  - title: `Garden Friends: Earthworms at Work`
  - category: Science / Gardening

Both files have SHA-256:

`e9821bdd4fd24a00abf2965d542287e7b969704501f1323acb10b62e9672dd56`

The actual image is an **animal-facts infographic**, so row 120's gardening/earthworm title and caption do not describe its media payload. This is not merely a repeated recommendation candidate; it is a source-to-metadata mismatch.

## Release decision

**DO NOT run production `--execute --publish` yet.**

The bundle adapter intentionally rejects duplicate media bytes, so the current full source gate will fail closed on this duplicate. This is the desired behavior.

Required correction before production ingestion:

1. Replace `Member3Gardening/fun-animal-facts-for-kids.jpg` with the intended earthworm/gardening image for CSV row 120, **or** remove/correct row 120 and regenerate the master CSV/count contract deliberately.
2. Re-run the combined two-part SHA-256/completeness/media-property validation.
3. Run LittleNet's moderation dry-run over the full corrected 206-item set.
4. Only after a clean dry-run proceed to private R2 upload + Neon catalog insertion + feed/reels streaming validation.

No production child-serving media has been uploaded as part of this validation.
