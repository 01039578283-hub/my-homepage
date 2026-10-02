# Learning guides

Scope: `/guide/` is the searchable directory of 65 articles. `/교육정보/` provides six reading paths and links to its 45 existing article URLs. Existing URLs and the 40 original article images are retained. Eight new articles use `/guide/` URLs.

Content is maintained in `learning_guide_content.py`. Each article has its own audience, explanation, activity, four record fields, next check, parent support, applicable limits, sources, and related articles. Research links point to 14 primary institutional resources verified on 2026-10-02. Examples are authored practice material, not student results or academy service claims.

`learning-guides-baseline.zip` contains only the 59 original public hub/article HTML files from commit `0a4fc2de25e80a520f0f0ed512b17ced4ebb3718`. It is an immutable input used to retain useful explanations and original images without repeatedly appending generated sections. All tools and this source archive are excluded from the public release.

Use Python with `lxml`, from the repository root:

```powershell
python -X utf8 tools/build_learning_guides.py --report-dir reports/learning-guides
```

This updates exactly 67 HTML files, 65 UTF-8 BOM/CRLF blank records, the two shared UI assets, the affected description mappings, sitemap entries, RSS articles, and reviewed release hashes. It never commits, pushes, deploys, or changes the authoring checkout. `DATE` should reflect an actual reviewed content update, not every deployment.

Whole-scope verification also needs `baseline.json` from the original audit. Verified audit files are at `C:/Users/1992k/Desktop/CodexData/outputs/wawa-learning-guides-20261002/`. Run:

```powershell
python -X utf8 tools/verify_learning_guides.py --report-dir C:/Users/1992k/Desktop/CodexData/outputs/wawa-learning-guides-20261002
node seo-descriptions.mjs --root=. --files-file=C:/Users/1992k/Desktop/CodexData/outputs/wawa-learning-guides-20261002/changed-html.json --check
```

Image URL checks compare decoded paths and all other attributes in the original order; HTML serialization percent-encodes Korean URL characters. Static verification checks every article, reference assignment, FAQ/schema pair, record file, internal link and release hash, as well as preservation of unrelated sitemap dates, description mappings and manifest entries. Browser checks cover every article at 320px, both hubs, larger breakpoints, filters, downloads, reset and printing.

Records have no API, browser storage or automatic persistence. The existing site tracker was checked on 2026-10-02: its pageview payload contains site/id/path/referrer/device and does not read record fields. Recheck if that external script changes.

Current implementation is local. Production still reflects the previously approved release until a new deployment is requested and verified.
