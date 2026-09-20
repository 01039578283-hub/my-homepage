// Verify the actual browser-delivered codec without any browser automation.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const root = path.resolve(__dirname, '..');
function load(name) {
  const source = fs.readFileSync(path.join(root, 'assets', name), 'utf8');
  const sandbox = { window: {} };
  vm.runInNewContext(source, sandbox, { timeout: 5000 });
  return { source, rows: JSON.parse(JSON.stringify(sandbox.window.WAWA_CENTER_INDEX)) };
}
const before = load('center-search-data.js');
const after = load('center-search-index.js');
assert.deepEqual(after.rows, before.rows);
assert.equal(after.rows.length, 6025);
const searchCode = fs.readFileSync(path.join(root, 'assets', 'center-search.js'), 'utf8');
const normalizeSource = searchCode.match(/function normalize\(value\) \{[\s\S]+?\n  \}/)[0];
const normalize = vm.runInNewContext('(' + normalizeSource + ')');
const queries = ['명일동', '강원', '고등 수학', '서울 영어', 'qzx없는지역'];
const results = [];
for (const query of queries) {
  const tokens = normalize(query).split(/\s+/);
  const search = rows => rows.filter(r => tokens.every(t => normalize(r.search).includes(t))).map(r => r.url);
  assert.deepEqual(search(before.rows), search(after.rows));
  results.push({ query, matches: search(after.rows).length });
}
for (const [oldLevel, newLevel] of [['초등', '초등학생'], ['중등', '중학생'], ['고등', '고등학생']]) {
  for (const subject of ['영어', '수학']) {
    const find = query => after.rows.filter(r => normalize(query).split(/\s+/).every(t => normalize(r.search).includes(t))).map(r => r.url);
    const oldQuery = oldLevel + ' ' + subject;
    const newQuery = newLevel + ' ' + subject;
    assert.deepEqual(find(oldQuery), find(newQuery));
    assert.equal(find(newQuery).length, 371);
    results.push({ query: newQuery, matches: find(newQuery).length, legacyQueryEquivalent: true });
  }
}
console.log(JSON.stringify({ entries: after.rows.length, identicalFields: true, queries: results,
  originalBytes: Buffer.byteLength(before.source), compactBytes: Buffer.byteLength(after.source),
  originalGzipBytes: zlib.gzipSync(before.source).length, compactGzipBytes: zlib.gzipSync(after.source).length }, null, 2));
