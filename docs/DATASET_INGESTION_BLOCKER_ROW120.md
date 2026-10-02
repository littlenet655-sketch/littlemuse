# Dataset ingestion blocker — row 120

The two supplied dataset bundles mechanically reconstruct to all 206 CSV rows, but production ingestion must remain fail-closed because one byte-identical media payload is assigned to two different metadata rows.

- Row 34: `Member3Animals.zip/fun-animal-facts-for-kids.jpg` — animal facts.
- Row 120: `Member3Gardening.zip/fun-animal-facts-for-kids.jpg` — metadata claims earthworms/gardening.
- Shared SHA-256: `e9821bdd4fd24a00abf2965d542287e7b969704501f1323acb10b62e9672dd56`.

Visual inspection confirms the payload is an animal-facts infographic, so row 120 is a media/metadata mismatch. The bundle staging adapter rejects duplicate media bytes and therefore correctly prevents `--execute --publish` until this source row is corrected.
