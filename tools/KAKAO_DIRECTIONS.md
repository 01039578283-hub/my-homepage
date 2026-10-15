# Kakao directions added 2026-10-15

- Public page URLs, canonical links, JSON-LD and all existing images are retained.
- Directions appear after the existing map image container, using one shared
  map document per branch in assets/branch-maps/.
- Each map document contains the supplied original Kakao roughmap snippet.
  Its wrapper adapts the width, retains attribution and map controls, and
  omits the provider's duplicate text listing. The presentation pass retains
  the heading and readable address and removes outbound navigation controls.
- Parent iframes use a shared deferred loader with a 300px viewport margin.
  Their data-kakao-src paths are extensionless to avoid cleanUrls redirects.
  Map documents are noindex,follow,
  excluded from the sitemap, visitor tracking and favicon page-count checks.
- The scoped directions CSS uses a specific scroll-margin override so the
  shared sticky navigation does not obscure the directions heading.
- The existing map area is reserved at 392px (420px on narrow screens).
  Maps load automatically; a noscript iframe provides fallback access. The loader
  falls back to immediate loading when IntersectionObserver is unavailable.
  Supplied map snippets and image assets remain byte-identical. New versioned
  wrappers hide outbound menus and neutralize generated anchor navigation while
  retaining map zoom controls, logos and attribution. Embedded frames restrict
  popups/top navigation with sandbox="allow-scripts allow-same-origin".
- Branch and neighborhood hub cards link directly to #branch-location.
- 화성태안점 has no supplied map snippet. Its existing map image is retained
  and its directions section retains the readable address
  경기 화성시 병점중앙로 87 408호. Do not substitute another branch's snippet.

Release output and verification evidence:
C:/Users/1992k/Desktop/CodexData/outputs/kakao-maps-release-20261015/.

Mobile performance follow-up, full validation and deployment evidence:
C:/Users/1992k/Desktop/CodexData/outputs/kakao-mobile-performance-20261015/.

Public files are allowlisted and hashed in release-public-manifest.json.
When updating a map document or stylesheet, create a new fingerprinted file,
update kakao-map-presentation.json and reviewed manifest hashes, and
run node favicon-build.mjs. This includes the existing analytics and
description passes. Keep map documents excluded from page-view tracking.

Map-only presentation (2026-10-15): release-public-build.mjs calls the scoped
kakao-map-presentation.mjs while copying the reviewed source snapshot. Original
authoring/release HTML stays untouched; the published output removes map CTA
anchors and explanatory paragraphs, updates versioned frame/CSS/JS references,
and keeps heading/address, original posters, map positions and public page URLs.
Expected scope counts are enforced before build completion. Preview and verify
the compiled .public-release output, not the raw source HTML.
Evidence: C:/Users/1992k/Desktop/CodexData/outputs/kakao-map-only-20261015/.
