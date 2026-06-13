const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

const ROOT = path.resolve(__dirname, '..');
const CONTESTS_DIR = path.join(ROOT, 'data', 'contests');
const MANIFEST_PATH = path.join(CONTESTS_DIR, 'manifest.json');

const PALETTE = [
  [-30.0, '#08306b'],
  [-20.0, '#08519c'],
  [-10.0, '#2171b5'],
  [-5.0, '#6baed6'],
  [5.0, '#cbd5e1'],
  [10.0, '#fcae91'],
  [20.0, '#fb6a4a'],
  [30.0, '#de2d26'],
];

const YEAR_SPECS = [
  {
    year: 2010,
    sourceFile: path.join(ROOT, 'data', '2010', '10gen_stwd_pct.xls'),
    sheets: [
      {
        sheetName: 'Lt Gov to Voting Statistics',
        partyRow: 3,
        candidateRow: 4,
        dataStartRow: 5,
        contests: [
          { contestType: 'lieutenant_governor', office: 'Lieutenant Governor', startCol: 1, endCol: 3 },
          { contestType: 'secretary_of_state', office: 'Secretary of State', startCol: 4, endCol: 5 },
          { contestType: 'state_controller', office: 'State Controller', startCol: 6, endCol: 7 },
          { contestType: 'state_treasurer', office: 'State Treasurer', startCol: 8, endCol: 8 },
          { contestType: 'attorney_general', office: 'Attorney General', startCol: 9, endCol: 9 },
          {
            contestType: 'superintendent_public_instruction',
            office: 'Superintendent of Public Instruction',
            startCol: 10,
            endCol: 11,
          },
        ],
      },
    ],
  },
  {
    year: 2014,
    sourceFile: path.join(ROOT, 'data', '2014', '14gen_stwd_pct.xls'),
    sheets: [
      {
        sheetName: 'Gov to St Cont',
        partyRow: 3,
        candidateRow: 4,
        dataStartRow: 5,
        contests: [
          { contestType: 'lieutenant_governor', office: 'Lieutenant Governor', startCol: 6, endCol: 8 },
          { contestType: 'secretary_of_state', office: 'Secretary of State', startCol: 9, endCol: 10 },
          { contestType: 'state_controller', office: 'State Controller', startCol: 11, endCol: 11 },
        ],
      },
      {
        sheetName: 'St Treasurer to Voting Stats',
        partyRow: 3,
        candidateRow: 4,
        dataStartRow: 5,
        contests: [
          { contestType: 'state_treasurer', office: 'State Treasurer', startCol: 1, endCol: 2 },
          { contestType: 'attorney_general', office: 'Attorney General', startCol: 3, endCol: 4 },
          {
            contestType: 'superintendent_public_instruction',
            office: 'Superintendent of Public Instruction',
            startCol: 5,
            endCol: 6,
          },
        ],
      },
    ],
  },
];

const MANAGED_CONTEST_TYPES = new Set(
  YEAR_SPECS.flatMap((yearSpec) => yearSpec.sheets.flatMap((sheet) => sheet.contests.map((contest) => contest.contestType)))
);

function cleanCell(value) {
  return String(value == null ? '' : value).replace(/\r?\n/g, ' ').trim();
}

function parseNumber(value) {
  const text = cleanCell(value).replace(/,/g, '').replace(/%/g, '');
  if (!text) return NaN;
  const num = Number(text);
  return Number.isFinite(num) ? num : NaN;
}

function isBlank(value) {
  return cleanCell(value) === '';
}

function normalizeCounty(value) {
  return cleanCell(value).replace(/\s+County$/i, '').toUpperCase();
}

function normalizePrecinct(value) {
  const text = cleanCell(value);
  if (!text) return '';
  const numeric = Number(text.replace(/,/g, ''));
  if (Number.isFinite(numeric) && String(numeric) === text) {
    return Number.isInteger(numeric) ? String(numeric) : text;
  }
  return text.toUpperCase();
}

function normalizeParty(value) {
  const text = cleanCell(value).toUpperCase().replace(/\./g, '');
  if (text.startsWith('DEM')) return 'DEM';
  if (text.startsWith('REP')) return 'REP';
  if (!text || text === 'NA') return '';
  return 'OTHER';
}

function pickColor(marginPct) {
  const signed = Number(marginPct) || 0;
  for (const [threshold, color] of PALETTE) {
    if (signed <= threshold) return color;
  }
  return '#a50f15';
}

function summarizeVotes(records) {
  let demVotes = 0;
  let repVotes = 0;
  let otherVotes = 0;
  let demCandidate = '';
  let repCandidate = '';

  for (const row of records) {
    const votes = Number(row.votes) || 0;
    if (row.partyNorm === 'DEM') {
      demVotes += votes;
      if (!demCandidate) demCandidate = row.candidate;
    } else if (row.partyNorm === 'REP') {
      repVotes += votes;
      if (!repCandidate) repCandidate = row.candidate;
    } else {
      otherVotes += votes;
    }
  }

  const totalVotes = demVotes + repVotes + otherVotes;
  const margin = repVotes - demVotes;
  const marginPct = totalVotes ? (margin / totalVotes) * 100 : 0;
  return {
    dem_votes: demVotes,
    rep_votes: repVotes,
    other_votes: otherVotes,
    total_votes: totalVotes,
    dem_candidate: demCandidate,
    rep_candidate: repCandidate,
    margin,
    margin_pct: Number(marginPct.toFixed(4)),
    winner: margin > 0 ? 'REP' : (margin < 0 ? 'DEM' : 'TIE'),
    color: pickColor(marginPct),
  };
}

function parseSheet(workbook, sheetSpec) {
  const sheet = workbook.Sheets[sheetSpec.sheetName];
  if (!sheet) {
    throw new Error(`Missing sheet "${sheetSpec.sheetName}"`);
  }
  const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false, defval: '' });
  const partyRow = rows[sheetSpec.partyRow] || [];
  const candidateRow = rows[sheetSpec.candidateRow] || [];
  const recordsByContest = new Map();
  let currentCounty = '';

  for (let i = sheetSpec.dataStartRow; i < rows.length; i += 1) {
    const row = rows[i] || [];
    const firstCell = cleanCell(row[0]);
    if (!firstCell) continue;

    const remaining = row.slice(1);
    const isCountyHeader = remaining.every(isBlank);
    if (isCountyHeader) {
      currentCounty = normalizeCounty(firstCell);
      continue;
    }
    if (!currentCounty) continue;

    const precinct = normalizePrecinct(firstCell);
    if (!precinct) continue;
    const rowKey = `${currentCounty} - ${precinct}`;

    for (const contest of sheetSpec.contests) {
      for (let col = contest.startCol; col <= contest.endCol; col += 1) {
        const candidate = cleanCell(candidateRow[col]);
        if (!candidate) continue;
        const votes = parseNumber(row[col]);
        if (!Number.isFinite(votes)) continue;
        const partyLabel = cleanCell(partyRow[col]);
        const record = {
          countyNorm: currentCounty,
          precinctNorm: precinct,
          rowKey,
          partyLabel,
          partyNorm: normalizeParty(partyLabel),
          candidate,
          votes: Math.trunc(votes),
        };
        if (!recordsByContest.has(contest.contestType)) recordsByContest.set(contest.contestType, []);
        recordsByContest.get(contest.contestType).push(record);
      }
    }
  }

  return recordsByContest;
}

function buildContestRows(records) {
  const grouped = new Map();
  for (const record of records) {
    if (!grouped.has(record.rowKey)) grouped.set(record.rowKey, []);
    grouped.get(record.rowKey).push(record);
  }
  return Array.from(grouped.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([rowKey, rows]) => ({ county: rowKey, ...summarizeVotes(rows) }));
}

function isContestedContest(rows) {
  return (rows || []).some((row) => {
    const demVotes = Number(row?.dem_votes) || 0;
    const repVotes = Number(row?.rep_votes) || 0;
    return demVotes > 0 && repVotes > 0;
  });
}

function readManifest() {
  const payload = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  return Array.isArray(payload.files) ? payload : { files: [] };
}

function upsertManifestEntries(manifest, entries) {
  const byKey = new Map();
  for (const entry of manifest.files || []) {
    if (MANAGED_CONTEST_TYPES.has(String(entry.contest_type || '')) && (Number(entry.year) === 2010 || Number(entry.year) === 2014)) {
      continue;
    }
    const key = `${Number(entry.year)}|${String(entry.contest_type || '')}`;
    byKey.set(key, entry);
  }
  for (const entry of entries) {
    const key = `${Number(entry.year)}|${String(entry.contest_type || '')}`;
    byKey.set(key, entry);
  }
  manifest.files = Array.from(byKey.values()).sort((a, b) => {
    const yearDiff = Number(a.year) - Number(b.year);
    return yearDiff || String(a.contest_type || '').localeCompare(String(b.contest_type || ''));
  });
}

function main() {
  const manifest = readManifest();
  const newEntries = [];

  for (const yearSpec of YEAR_SPECS) {
    for (const contestType of MANAGED_CONTEST_TYPES) {
      const outPath = path.join(CONTESTS_DIR, `${contestType}_${yearSpec.year}.json`);
      if (fs.existsSync(outPath)) fs.unlinkSync(outPath);
    }
  }

  for (const yearSpec of YEAR_SPECS) {
    if (!fs.existsSync(yearSpec.sourceFile)) {
      throw new Error(`Missing source workbook: ${yearSpec.sourceFile}`);
    }
    const workbook = XLSX.readFile(yearSpec.sourceFile);
    const contestRecords = new Map();
    const officeByContestType = new Map();

    for (const sheetSpec of yearSpec.sheets) {
      const parsed = parseSheet(workbook, sheetSpec);
      for (const contest of sheetSpec.contests) {
        officeByContestType.set(contest.contestType, contest.office);
      }
      for (const [contestType, rows] of parsed.entries()) {
        if (!contestRecords.has(contestType)) contestRecords.set(contestType, []);
        contestRecords.get(contestType).push(...rows);
      }
    }

    for (const [contestType, records] of Array.from(contestRecords.entries()).sort()) {
      const rows = buildContestRows(records);
      if (!rows.length) continue;
      if (!isContestedContest(rows)) {
        console.log(`Skipping uncontested ${contestType}_${yearSpec.year}`);
        continue;
      }
      const outName = `${contestType}_${yearSpec.year}.json`;
      const outPath = path.join(CONTESTS_DIR, outName);
      const payload = {
        year: yearSpec.year,
        contest_type: contestType,
        meta: {
          office: officeByContestType.get(contestType) || contestType,
          source: path.basename(yearSpec.sourceFile),
          aggregation: 'precinct',
        },
        rows,
      };
      fs.writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
      newEntries.push({
        year: yearSpec.year,
        contest_type: contestType,
        file: outName,
      });
      console.log(`Wrote ${outName} (${rows.length} rows)`);
    }
  }

  upsertManifestEntries(manifest, newEntries);
  fs.writeFileSync(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
  console.log(`Updated manifest with ${newEntries.length} entries`);
}

main();
