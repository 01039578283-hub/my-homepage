# Kakao directions added 2026-10-15

- Public page URLs, canonical links, JSON-LD and all existing images are retained.
- Directions appear after the existing map image container, using one shared
  map document per branch in assets/branch-maps/.
- Each map document contains the supplied original Kakao roughmap snippet.
  Its wrapper adapts the width, retains attribution and map controls, and
  omits the provider's duplicate text listing. Public address and directions
  links remain visible on the parent page.
- Parent iframes use a shared deferred loader with a 300px viewport margin.
  Their data-kakao-src paths are extensionless to avoid cleanUrls redirects.
  Map documents are noindex,follow,
  excluded from the sitemap, visitor tracking and favicon page-count checks.
- The scoped directions CSS uses a specific scroll-margin override so the
  shared sticky navigation does not obscure the directions heading.
- The existing map area is reserved at 392px (420px on narrow screens).
  A manual load link and a noscript iframe provide fallback access. The loader
  falls back to immediate loading when IntersectionObserver is unavailable.
  Original map documents, snippets and image assets remain byte-identical.
- Branch and neighborhood hub cards link directly to #branch-location.
- 화성태안점 has no supplied map snippet. Its existing map image is retained
  and its directions section links to Kakao address search for
  경기 화성시 병점중앙로 87 408호. Do not substitute another branch's snippet.

Release output and verification evidence:
C:/Users/1992k/Desktop/CodexData/outputs/kakao-maps-release-20261015/.

Mobile performance follow-up, full validation and deployment evidence:
C:/Users/1992k/Desktop/CodexData/outputs/kakao-mobile-performance-20261015/.

Public files are allowlisted and hashed in release-public-manifest.json.
When updating a map document or stylesheet, create a new fingerprinted file,
update the matching parent-page references and reviewed manifest hashes, and
run node favicon-build.mjs. This includes the existing analytics and
description passes. Keep map documents excluded from page-view tracking.
