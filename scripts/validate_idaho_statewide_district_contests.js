const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const CONTESTS_DIR = path.join(DATA_DIR, 'contests');
const REPORTS_DIR = path.join(DATA_DIR, 'reports');

const SOURCES = [
  {
    label: '2024-lines',
    dir: path.join(DATA_DIR, 'district_contests_2024_lines'),
    manifest: path.join(DATA_DIR, 'district_contests_2024_lines', 'manifest.json'),
  },
  {
    label: '2026-lines',
    dir: path.join(DATA_DIR, 'district_contests_2026_lines'),
    manifest: path.join(DATA_DIR, 'district_contests_2026_lines', 'manifest.json'),
  },
];

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function readCsvRowCount(filePath) {
  if (!fs.existsSync(filePath)) return 0;
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean);
  return Math.max(0, lines.length - 1);
}

function asNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function percent(value) {
  return Number.isFinite(Number(value)) ? Number(Number(value).toFixed(2)) : null;
}

function csvEscape(value) {
  const s = String(value == null ? '' : value);
  if (/[",\r\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function buildExpectedCounts() {
  const congressional = 2;
  const stateHouse = readCsvRowCount(path.join(DATA_DIR, 'id_state_house_districts.csv')) || 35;
  const stateSenate = readCsvRowCount(path.join(DATA_DIR, 'id_state_senate_districts.csv')) || 35;
  return {
    congressional,
    state_house: stateHouse,
    state_senate: stateSenate,
  };
}

function buildSourceContestIndex() {
  const manifest = readJson(path.join(CONTESTS_DIR, 'manifest.json'));
  const index = new Map();
  for (const entry of manifest.files || []) {
    const contestType = String(entry.contest_type || '').trim();
    const year = Number(entry.year);
    const file = String(entry.file || '').trim();
    if (!contestType || !Number.isFinite(year) || !file) continue;
    const fullPath = path.join(CONTESTS_DIR, file);
    if (!fs.existsSync(fullPath)) continue;
    const payload = readJson(fullPath);
    const rows = Array.isArray(payload.rows) ? payload.rows : [];
    const sourceTotalVotes = rows.reduce((sum, row) => sum + asNumber(row.total_votes), 0);
    index.set(`${contestType}__${year}`, {
      sourceFile: file,
      office: payload?.meta?.office || entry.office || contestType,
      sourceTotalVotes,
      rowCount: rows.length,
    });
  }
  return index;
}

function validateManifestSource(source, expectedCounts, sourceContestIndex) {
  const manifest = readJson(source.manifest);
  const rows = [];

  for (const entry of manifest.files || []) {
    const scope = String(entry.scope || '').trim();
    const file = String(entry.file || '').trim();
    const contestType = String(entry.contest_type || '').trim();
    const year = Number(entry.year);
    if (!scope || !file || !contestType || !Number.isFinite(year)) continue;

    const fullPath = path.join(source.dir, file);
    if (!fs.existsSync(fullPath)) continue;

    const payload = readJson(fullPath);
    const results = payload?.general?.results || {};
    const districtIds = Object.keys(results)
      .map((key) => Number(key))
      .filter((n) => Number.isFinite(n))
      .sort((a, b) => a - b);

    const expectedCount = Number(expectedCounts[scope]) || 0;
    const expectedIds = Array.from({ length: expectedCount }, (_, idx) => idx + 1);
    const presentSet = new Set(districtIds);
    const missingIds = expectedIds.filter((id) => !presentSet.has(id));
    const unexpectedIds = districtIds.filter((id) => id < 1 || id > expectedCount);

    let aggregateTotalVotes = 0;
    let noDataDistricts = 0;
    for (const key of Object.keys(results)) {
      const row = results[key] || {};
      const totalVotes = asNumber(row.total_votes);
      aggregateTotalVotes += totalVotes;
      if (row.no_data || totalVotes <= 0) noDataDistricts += 1;
    }

    const sourceMeta = sourceContestIndex.get(`${contestType}__${year}`) || null;
    const sourceTotalVotes = sourceMeta ? asNumber(sourceMeta.sourceTotalVotes) : 0;
    const recomputedCoveragePct = sourceTotalVotes > 0
      ? percent((aggregateTotalVotes / sourceTotalVotes) * 100)
      : null;

    rows.push({
      manifest_label: source.label,
      scope,
      year,
      contest_type: contestType,
      office: payload?.meta?.office || entry.office || (sourceMeta?.office || contestType),
      file,
      expected_districts: expectedCount,
      present_districts: districtIds.length,
      missing_districts: missingIds,
      unexpected_districts: unexpectedIds,
      no_data_districts: noDataDistricts,
      source_total_votes: sourceTotalVotes,
      aggregated_total_votes: aggregateTotalVotes,
      recomputed_coverage_pct: recomputedCoveragePct,
      meta_weighted_vote_coverage_pct: percent(payload?.meta?.weighted_vote_coverage_pct),
      meta_match_coverage_pct: percent(payload?.meta?.match_coverage_pct),
      complete_district_set: missingIds.length === 0 && unexpectedIds.length === 0,
      source_file: sourceMeta?.sourceFile || '',
    });
  }

  return rows;
}

function writeReports(rows) {
  fs.mkdirSync(REPORTS_DIR, { recursive: true });

  const jsonPath = path.join(REPORTS_DIR, 'district_contest_validation_report.json');
  fs.writeFileSync(jsonPath, `${JSON.stringify({ generated_at: new Date().toISOString(), files: rows }, null, 2)}\n`, 'utf8');

  const csvHeaders = [
    'manifest_label',
    'scope',
    'year',
    'contest_type',
    'office',
    'file',
    'expected_districts',
    'present_districts',
    'missing_districts_count',
    'missing_districts',
    'unexpected_districts_count',
    'unexpected_districts',
    'no_data_districts',
    'source_total_votes',
    'aggregated_total_votes',
    'recomputed_coverage_pct',
    'meta_weighted_vote_coverage_pct',
    'meta_match_coverage_pct',
    'complete_district_set',
    'source_file',
  ];
  const csvLines = [csvHeaders.join(',')];
  for (const row of rows) {
    csvLines.push([
      row.manifest_label,
      row.scope,
      row.year,
      row.contest_type,
      row.office,
      row.file,
      row.expected_districts,
      row.present_districts,
      row.missing_districts.length,
      row.missing_districts.join('|'),
      row.unexpected_districts.length,
      row.unexpected_districts.join('|'),
      row.no_data_districts,
      row.source_total_votes,
      row.aggregated_total_votes,
      row.recomputed_coverage_pct ?? '',
      row.meta_weighted_vote_coverage_pct ?? '',
      row.meta_match_coverage_pct ?? '',
      row.complete_district_set,
      row.source_file,
    ].map(csvEscape).join(','));
  }
  const csvPath = path.join(REPORTS_DIR, 'district_contest_validation_summary.csv');
  fs.writeFileSync(csvPath, `${csvLines.join('\n')}\n`, 'utf8');

  return { jsonPath, csvPath };
}

function printSummary(rows) {
  const incomplete = rows.filter((row) => !row.complete_district_set);
  const lowestCoverage = rows
    .filter((row) => Number.isFinite(row.recomputed_coverage_pct))
    .sort((a, b) => a.recomputed_coverage_pct - b.recomputed_coverage_pct)
    .slice(0, 12);

  console.log(`Validated ${rows.length} generated district contest files.`);
  console.log(`Incomplete district sets: ${incomplete.length}`);
  console.log('Lowest vote coverage files:');
  for (const row of lowestCoverage) {
    console.log(
      `- ${row.manifest_label} ${row.scope} ${row.contest_type} ${row.year}: ` +
      `${row.recomputed_coverage_pct}% coverage, ${row.no_data_districts} no-data districts`
    );
  }
}

function main() {
  const expectedCounts = buildExpectedCounts();
  const sourceContestIndex = buildSourceContestIndex();
  const rows = SOURCES.flatMap((source) => validateManifestSource(source, expectedCounts, sourceContestIndex));
  const outputs = writeReports(rows);
  printSummary(rows);
  console.log(`Wrote ${outputs.jsonPath}`);
  console.log(`Wrote ${outputs.csvPath}`);
}

main();
