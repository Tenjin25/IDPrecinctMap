const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');

const MANIFEST_SPECS = [
  {
    manifestPath: path.join(ROOT, 'data', 'contests', 'manifest.json'),
    baseDir: path.join(ROOT, 'data', 'contests'),
    kind: 'rows',
  },
  {
    manifestPath: path.join(ROOT, 'data', 'district_contests', 'manifest.json'),
    baseDir: path.join(ROOT, 'data', 'district_contests'),
    kind: 'district',
  },
  {
    manifestPath: path.join(ROOT, 'data', 'district_contests_2024_lines', 'manifest.json'),
    baseDir: path.join(ROOT, 'data', 'district_contests_2024_lines'),
    kind: 'district',
  },
  {
    manifestPath: path.join(ROOT, 'data', 'district_contests_2026_lines', 'manifest.json'),
    baseDir: path.join(ROOT, 'data', 'district_contests_2026_lines'),
    kind: 'district',
  },
];

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function sumCountyRows(rows) {
  let dem = 0;
  let rep = 0;
  let other = 0;
  for (const row of rows || []) {
    dem += Number(row?.dem_votes) || 0;
    rep += Number(row?.rep_votes) || 0;
    other += Number(row?.other_votes) || 0;
  }
  return { dem, rep, other };
}

function sumDistrictRows(payload) {
  const results = payload?.general?.results || {};
  let dem = 0;
  let rep = 0;
  let other = 0;
  for (const row of Object.values(results)) {
    dem += Number(row?.dem_votes) || 0;
    rep += Number(row?.rep_votes) || 0;
    other += Number(row?.other_votes) || 0;
  }
  return { dem, rep, other };
}

function isContested(entry, payload, kind) {
  const totals = kind === 'district'
    ? sumDistrictRows(payload)
    : sumCountyRows(payload?.rows || []);
  return totals.dem > 0 && totals.rep > 0;
}

function describeEntry(entry) {
  const scope = entry.scope ? `${entry.scope} ` : '';
  return `${entry.year} ${scope}${entry.contest_type} (${entry.file})`;
}

function main() {
  for (const spec of MANIFEST_SPECS) {
    if (!fs.existsSync(spec.manifestPath)) continue;
    const manifest = loadJson(spec.manifestPath);
    const entries = Array.isArray(manifest.files) ? manifest.files : [];
    const kept = [];
    const removed = [];

    for (const entry of entries) {
      const fileName = String(entry?.file || '').trim();
      if (!fileName) {
        kept.push(entry);
        continue;
      }
      const filePath = path.join(spec.baseDir, fileName);
      if (!fs.existsSync(filePath)) {
        kept.push(entry);
        continue;
      }

      let payload = null;
      try {
        payload = loadJson(filePath);
      } catch (err) {
        console.warn(`Could not parse ${filePath}: ${err.message}`);
        kept.push(entry);
        continue;
      }

      if (isContested(entry, payload, spec.kind)) {
        kept.push(entry);
      } else {
        removed.push(entry);
      }
    }

    manifest.files = kept;
    fs.writeFileSync(spec.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');

    console.log(`Updated ${path.relative(ROOT, spec.manifestPath)}`);
    if (!removed.length) {
      console.log('  Removed 0 uncontested entries');
      continue;
    }
    console.log(`  Removed ${removed.length} uncontested entries:`);
    for (const entry of removed) {
      console.log(`  - ${describeEntry(entry)}`);
    }
  }
}

main();
