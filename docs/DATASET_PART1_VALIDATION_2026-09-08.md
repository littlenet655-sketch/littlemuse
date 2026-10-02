# LittleNet Dataset Part 1 Validation — 2026-09-08

Validated source bundle: `LittleNet_Dataset_Part1_of_2.zip` supplied out-of-band for ingestion testing. The dataset bytes are **not** committed to GitHub.

## Bundle contents

- Total files in bundle: **97**
- Master CSV: **1** (`littlenet_dataset_captions.csv`)
- Media files: **96**
  - `Member3Animals`: **58**
  - `Member3Crafts&Hobbies`: **26**
  - `18+images`: **12**

## Master CSV checks

- Rows: **206**
- Columns: **24**
- Expected archive counts:
  - `family.zip`: 74
  - `Member3Animals.zip`: 58
  - `Member3Crafts&Hobbies.zip`: 26
  - `Member3Gardening.zip`: 21
  - `Member3Cooking.zip`: 15
  - `18+images.zip`: 12
- Moderation labels: **194 ALLOWED / 12 BLOCKED**
- Media types: **127 VIDEO / 79 IMAGE**
- Reel flags: **122 reels / 84 non-reels**

## Part 1 media checks

All **96/96** media files in Part 1 were matched exactly to their master CSV rows.

- Part 1 moderation distribution: **84 ALLOWED / 12 BLOCKED**
- Part 1 media types: **55 VIDEO / 41 IMAGE**
- File-size checks against CSV: **96/96 pass**
- Image/video width and height checks against CSV: **96/96 pass**
- Video duration checks against CSV (0.15s tolerance): **55/55 pass**
- Duplicate SHA-256 payloads within Part 1: **0**
- Unreadable image/video files: **0**

## Remaining Part 2 expectation

The master CSV indicates the remaining bundle must supply exactly **110** media files:

- `family.zip`: **74**
- `Member3Gardening.zip`: **21**
- `Member3Cooking.zip`: **15**

Production ingestion must remain blocked until Part 2 completes the exact **206/206** source-file gate and the full dry-run passes current LittleNet moderation.
