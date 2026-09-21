# Neighborhood subject hubs, 2026-09-21

- 371 neighborhoods, 742 subject hubs, 2,226 existing school-stage pages.
- New hierarchy: `/지점안내/{지역}/{지점}/{동네}{수학|영어}학원/{초등|중등|고등}/`.
- `hubs.json` records manuscript provenance and the center mapping.
- `url-migration.json` records every old and new school-stage URL. The old files are removed only after the article, images and course conditions are checked unchanged.
- Publication dates of moved articles remain unchanged. New hubs have their own publication history. Rebuilds do not advance modification dates.
- Twelve Vercel redirect rules use percent-encoded literals to cover the six school-stage/subject patterns and their `index.html` forms. Old and new Korean/encoded URLs must be tested on a deployment.

## Maintenance

Run `python tools/migrate_local_subject_hubs.py --refresh-hubs` to rebuild only the subject hubs from the two original ZIPs under the user's `새 홈페이지 원고 작업용` folder. Run `--write` for the complete idempotent migration pipeline. Neither mode regenerates the original grade manuscripts from a different archive.

Run `python tools/audit_local_subject_hubs.py` and `python -m unittest discover -s tools -p test_local_subject_hubs.py` before release. The bundled Python runtime provides lxml/openpyxl/Pillow. Older manuscript-editorial tests depend on the original six historical archives; do not substitute revised files with identical names.

`python tools/export_branch_subject_urls.py` exports a UTF-8 Korean URL list to Desktop: main, branch directory, all regions, all centers, all neighborhood subject hubs, then three school-stage children grouped by hub. The branch tree contains 3,178 URLs; with the main URL the file contains 3,179 lines. Existing non-branch route families are intentionally excluded.

The education-focused RSS remains an article feed; the complete sitemap contains the new hubs and migrated school-stage URLs.
