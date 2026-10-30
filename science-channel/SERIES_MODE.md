# Fictional series mode

This adds a separate serialized-fiction planner. Educational topic workflows remain unchanged.

## Create the first part
1. Open Actions → Science Channel — Create Fictional Series Part.
2. Run it on the adaptive-cinematic-effects branch.
3. Enter a series title, genre, season 1 and part 1.
4. The planner creates a series bible, recurring character references, 48 narration scenes, 48 image prompts and continuity notes.
5. Generate and upload exactly 48 images to the part's images/incoming/ folder.
6. Render with the existing episode renderer using the new part folder as its episode path.

## Continue the story
Run the workflow again with the same series_slug and the next season/part numbers. Leave series_title blank for an existing series. It reads series.json and previous continuity.json files to carry characters, world rules, story events and unresolved threads forward. Existing parts are never overwritten.

## First-version limits
- One part is generated per workflow run; all eight parts are not generated in one run.
- Each part has 48 scenes for the current 8–10 minute renderer.
- Image generation and upload remain manual.
- This workflow pushes only to adaptive-cinematic-effects, never main.
