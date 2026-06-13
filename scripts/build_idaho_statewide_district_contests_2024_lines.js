const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'data');
const CONTESTS_DIR = path.join(DATA_DIR, 'contests');
const OUT_2024_DIR = path.join(DATA_DIR, 'district_contests_2024_lines');
const OUT_2026_DIR = path.join(DATA_DIR, 'district_contests_2026_lines');
const MANIFEST_2024_PATH = path.join(OUT_2024_DIR, 'manifest.json');
const MANIFEST_2026_PATH = path.join(OUT_2026_DIR, 'manifest.json');
const COUNTY_GEOJSON_PATH = path.join(DATA_DIR, 'census', 'tl_2020_16_county.geojson');
const PRECINCT_2020_PATH = path.join(DATA_DIR, 'census', 'tl_2020_16_vtd20.geojson');
const PRECINCT_2008_PATH = path.join(DATA_DIR, 'precinct_centroids_2008.geojson');
const LEGISLATIVE_2022_WORKBOOK_PATH = path.join(
  DATA_DIR,
  '2022_General_Canvass',
  '2022_General_Canvass',
  '22 General Legislative - Precinct.xlsx'
);
const STATEWIDE_2022_WORKBOOK_PATH = path.join(
  DATA_DIR,
  '2022_General_Canvass',
  '2022_General_Canvass',
  '22 General Statewide - Precinct.xlsx'
);

const CROSSWALKS = {
  congressional: {
    prefix: 'congressional',
    modern: path.join(DATA_DIR, 'crosswalks', 'precinct_to_cd119_from_2020_vtd20_nhgis_popweighted.csv'),
    legacy: path.join(DATA_DIR, 'crosswalks', 'precinct_to_cd119_from_2008_vtd00_nhgis_popweighted.csv'),
  },
  state_house: {
    prefix: 'state_house',
    modern: path.join(DATA_DIR, 'crosswalks', 'precinct_to_2024_state_house_from_2020_vtd20_nhgis_popweighted.csv'),
    legacy: path.join(DATA_DIR, 'crosswalks', 'precinct_to_2024_state_house_from_2008_vtd00_nhgis_popweighted.csv'),
  },
  state_senate: {
    prefix: 'state_senate',
    modern: path.join(DATA_DIR, 'crosswalks', 'precinct_to_2024_state_senate_from_2020_vtd20_nhgis_popweighted.csv'),
    legacy: path.join(DATA_DIR, 'crosswalks', 'precinct_to_2024_state_senate_from_2008_vtd00_nhgis_popweighted.csv'),
  },
};

const MANAGED_SCOPES = new Set(Object.keys(CROSSWALKS));
const MANAGED_CONTEST_TYPES = new Set([
  'president',
  'governor',
  'us_senate',
  'lieutenant_governor',
  'secretary_of_state',
  'state_controller',
  'state_treasurer',
  'attorney_general',
  'superintendent_public_instruction',
]);
const MIN_YEAR = 2000;
const MAX_YEAR = 2024;

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

function clean(value) {
  return String(value == null ? '' : value).trim();
}

function upper(value) {
  return clean(value).toUpperCase();
}

function normalizeCountyToken(value) {
  let out = upper(value).replace(/\s+/g, ' ');
  out = out.replace(/\bCONT\.?/g, '').replace(/\s+/g, ' ').trim();
  return out;
}

function parseCsv(text) {
  const lines = String(text || '').split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const headers = lines[0].split(',');
  return lines.slice(1).map((line) => {
    const cols = line.split(',');
    const row = {};
    headers.forEach((header, idx) => {
      row[header] = cols[idx] ?? '';
    });
    return row;
  });
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function pickColor(marginPct) {
  const signed = Number(marginPct) || 0;
  for (const [threshold, color] of PALETTE) {
    if (signed <= threshold) return color;
  }
  return '#a50f15';
}

function buildNumericVariants(rawValue) {
  const variants = new Set();
  const value = upper(rawValue);
  const digits = value.replace(/\D/g, '');
  if (!digits) return variants;
  variants.add(digits);
  const trimmed = digits.replace(/^0+/, '') || '0';
  variants.add(trimmed);
  [2, 3, 4, 6].forEach((width) => variants.add(trimmed.padStart(width, '0')));
  return variants;
}

function compactAlphaNumeric(value) {
  return upper(value).replace(/[^A-Z0-9]/g, '');
}

function directionalNameVariants(rawValue) {
  const out = new Set();
  const raw = upper(rawValue);
  if (!raw) return out;
  const compact = compactAlphaNumeric(raw);
  if (compact) out.add(compact);

  const replacements = [
    [/^EAST\s+/, 'E '],
    [/^WEST\s+/, 'W '],
    [/^NORTH\s+/, 'N '],
    [/^SOUTH\s+/, 'S '],
    [/\s+EAST\s+/g, ' E '],
    [/\s+WEST\s+/g, ' W '],
    [/\s+NORTH\s+/g, ' N '],
    [/\s+SOUTH\s+/g, ' S '],
    [/\bSIDE\b/g, 'SIDE'],
    [/\bCITY\b/g, ''],
    [/\bVALLEY\b/g, ''],
    [/\bBENCH\b/g, ''],
  ];

  let current = raw;
  for (const [pattern, replacement] of replacements) {
    current = current.replace(pattern, replacement).replace(/\s+/g, ' ').trim();
    if (current) {
      out.add(current);
      const compactCurrent = compactAlphaNumeric(current);
      if (compactCurrent) out.add(compactCurrent);
    }
  }
  return out;
}

function addAlias(aliasMap, countyNorm, alias, precinctKey) {
  const county = normalizeCountyToken(countyNorm);
  const key = upper(alias);
  const precinct = clean(precinctKey);
  if (!county || !key || !precinct) return;
  if (!aliasMap.has(county)) aliasMap.set(county, new Map());
  const countyMap = aliasMap.get(county);
  if (!countyMap.has(key)) countyMap.set(key, new Set());
  countyMap.get(key).add(precinct);
}

function addAliasVariants(aliasMap, countyNorm, alias, precinctKey) {
  const normalizedAlias = upper(alias);
  if (!normalizedAlias) return;
  addAlias(aliasMap, countyNorm, normalizedAlias, precinctKey);
  if (/^\d+$/.test(normalizedAlias)) {
    for (const numeric of buildNumericVariants(normalizedAlias)) {
      addAlias(aliasMap, countyNorm, numeric, precinctKey);
    }
    if (normalizedAlias.length > 3) {
      for (const slice of [normalizedAlias.slice(-3), normalizedAlias.slice(-2)]) {
        if (!slice) continue;
        for (const numeric of buildNumericVariants(slice)) {
          addAlias(aliasMap, countyNorm, numeric, precinctKey);
        }
      }
    }
  }
  const trailingNumeric = normalizedAlias.match(/\b0*([0-9]{1,4})$/);
  if (trailingNumeric) {
    for (const numeric of buildNumericVariants(trailingNumeric[1])) {
      addAlias(aliasMap, countyNorm, numeric, precinctKey);
    }
  }
  const leadingNumericName = normalizedAlias.match(/^0*[0-9]{1,4}\s+(.+)$/);
  if (leadingNumericName?.[1]) {
    addAlias(aliasMap, countyNorm, leadingNumericName[1], precinctKey);
  }
  const trailingNumericName = normalizedAlias.match(/^(.+?)\s+0*[0-9]{1,4}$/);
  if (trailingNumericName?.[1]) {
    addAlias(aliasMap, countyNorm, trailingNumericName[1].trim(), precinctKey);
  }
  for (const variant of directionalNameVariants(normalizedAlias)) {
    addAlias(aliasMap, countyNorm, variant, precinctKey);
  }
}

function readCountyNameByFips() {
  const geojson = readJson(COUNTY_GEOJSON_PATH);
  const out = new Map();
  for (const feature of geojson.features || []) {
    const props = feature?.properties || {};
    const countyFips = clean(props.COUNTYFP).padStart(3, '0');
    const countyName = normalizeCountyToken(props.NAME || props.NAMELSAD || props.county_nam || '');
    if (countyFips && countyName) out.set(countyFips, countyName);
  }
  return out;
}

function readCountyFipsByName() {
  const byFips = readCountyNameByFips();
  const out = new Map();
  for (const [countyFips, countyName] of byFips.entries()) {
    out.set(countyName, countyFips);
  }
  return out;
}

function readModernCountyByPrecinctKey() {
  const geojson = readJson(PRECINCT_2020_PATH);
  const out = new Map();
  for (const feature of geojson.features || []) {
    const props = feature?.properties || {};
    const precinctKey = clean(
      props.GEOID20
      || props.GEOID
      || `${clean(props.STATEFP20)}${clean(props.COUNTYFP20)}${clean(props.VTDST20)}`
    );
    const countyNorm = normalizeCountyToken(props.county_nam || '');
    if (precinctKey && countyNorm) out.set(precinctKey, countyNorm);
  }
  return out;
}

function loadModernPrecinctResolver() {
  const geojson = readJson(PRECINCT_2020_PATH);
  const aliasMap = new Map();

  for (const feature of geojson.features || []) {
    const props = feature?.properties || {};
    const countyNorm = normalizeCountyToken(props.county_nam || '');
    const precinctKey = clean(
      props.GEOID20
      || props.GEOID
      || `${clean(props.STATEFP20)}${clean(props.COUNTYFP20)}${clean(props.VTDST20)}`
    );
    if (!countyNorm || !precinctKey) continue;

    const aliases = new Set([
      props.precinct_norm,
      props.prec_id,
      props.VTDST20,
      props.NAME20,
      props.NAMELSAD20,
      props.precinct_name,
    ].map(upper).filter(Boolean));

    for (const alias of aliases) addAliasVariants(aliasMap, countyNorm, alias, precinctKey);
  }

  return aliasMap;
}

function loadLegacyPrecinctResolver() {
  const geojson = readJson(PRECINCT_2008_PATH);
  const countyNameByFips = readCountyNameByFips();
  const aliasMap = new Map();

  for (const feature of geojson.features || []) {
    const props = feature?.properties || {};
    const countyFips = clean(props.COUNTYFP00).padStart(3, '0');
    const countyNorm = countyNameByFips.get(countyFips) || '';
    const code = upper(props.NAME00 || '');
    if (!countyNorm || !code) continue;
    let precinctKey = '';
    if (/^\d{6}$/.test(code) && code.startsWith(countyFips)) {
      precinctKey = `16${countyFips}${code}`;
    } else {
      const codeDigits = (code.match(/(\d{1,3})$/)?.[1] || code.match(/(\d+)/)?.[1] || '').padStart(3, '0');
      precinctKey = codeDigits
        ? `16${countyFips}${countyFips}${codeDigits}`
        : `16${countyFips}${code}`;
    }
    addAliasVariants(aliasMap, countyNorm, code, precinctKey);
  }

  return aliasMap;
}

function load2022LegislativeWorkbookResolver() {
  const byCounty = new Map();
  if (!fs.existsSync(LEGISLATIVE_2022_WORKBOOK_PATH)) return byCounty;

  const workbook = XLSX.readFile(LEGISLATIVE_2022_WORKBOOK_PATH);
  for (const sheetName of workbook.SheetNames || []) {
    const districtMatch = clean(sheetName).match(/^Leg Dist (\d+)$/i);
    if (!districtMatch) continue;
    const districtNum = Number(districtMatch[1]);
    if (!Number.isFinite(districtNum) || districtNum <= 0) continue;

    const rows = XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], {
      header: 1,
      raw: false,
      defval: '',
    });

    let currentCounty = '';
    for (const row of rows) {
      const firstCell = upper(row?.[0]);
      if (!firstCell) continue;

      const remaining = (row || []).slice(1).map((value) => clean(value));
      const hasNumericPayload = remaining.some((value) => /^-?\d+(?:\.\d+)?$/.test(value));
      if (
        !hasNumericPayload
        && !firstCell.startsWith('LEGISLATIVE DIST')
        && firstCell !== 'PRECINCT'
        && firstCell !== 'ST SEN'
        && firstCell !== 'ST REP A'
        && firstCell !== 'ST REP B'
        && !['REP', 'DEM'].includes(firstCell)
        && /^[A-Z .&'/-]+$/.test(firstCell)
      ) {
        currentCounty = normalizeCountyToken(firstCell);
        continue;
      }

      if (!currentCounty || !hasNumericPayload) continue;
      if (firstCell.includes('CO. TOTAL') || firstCell.includes('CO TOTAL')) continue;
      if (!byCounty.has(currentCounty)) byCounty.set(currentCounty, new Map());
      byCounty.get(currentCounty).set(firstCell, districtNum);
    }
  }

  return byCounty;
}

function load2022CongressionalWorkbookResolver() {
  const byCounty = new Map();
  if (!fs.existsSync(STATEWIDE_2022_WORKBOOK_PATH)) return byCounty;

  const workbook = XLSX.readFile(STATEWIDE_2022_WORKBOOK_PATH);
  for (const [sheetName, districtNum] of [['US Rep 1', 1], ['US Rep 2', 2]]) {
    if (!workbook.SheetNames.includes(sheetName)) continue;
    const rows = XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], {
      header: 1,
      raw: false,
      defval: '',
    });

    let currentCounty = '';
    for (const row of rows) {
      const firstCell = upper(row?.[0]);
      if (!firstCell) continue;

      const remaining = (row || []).slice(1).map((value) => clean(value));
      const hasNumericPayload = remaining.some((value) => /^-?\d+(?:\.\d+)?$/.test(value));
      if (
        !hasNumericPayload
        && firstCell !== 'PRECINCT'
        && firstCell !== 'UNITED STATES'
        && firstCell !== 'REPRESENTATIVE'
        && !firstCell.startsWith('DISTRICT ')
        && !['DEM', 'REP', 'LIB'].includes(firstCell)
        && /^[A-Z .&'/-]+$/.test(firstCell)
      ) {
        currentCounty = normalizeCountyToken(firstCell);
        continue;
      }

      if (!currentCounty || !hasNumericPayload) continue;
      if (firstCell.includes('CO. TOTAL') || firstCell.includes('CO TOTAL')) continue;
      if (!byCounty.has(currentCounty)) byCounty.set(currentCounty, new Map());
      byCounty.get(currentCounty).set(firstCell, districtNum);
    }
  }

  return byCounty;
}

function addContestDerivedAliasBridges(sourceManifest, resolvers) {
  for (const entry of sourceManifest.files || []) {
    const sourcePath = path.join(CONTESTS_DIR, clean(entry.file));
    if (!fs.existsSync(sourcePath)) continue;
    const payload = readJson(sourcePath);
    if (!isPrecinctContestPayload(payload)) continue;

    for (const row of payload.rows || []) {
      const normalized = normalizeCountyToken(row.county);
      if (!normalized.includes(' - ')) continue;
      const [countyNorm, rawToken] = normalized.split(' - ', 2);
      const rawUpper = upper(rawToken);
      const cleanedToken = rawUpper
        .replace(/[#.]/g, ' ')
        .replace(/\s*-\s*/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      const prefixNumberedMatch = rawUpper.match(/^#?0*([0-9]{1,4})\s+(.+)$/)
        || cleanedToken.match(/^#?0*([0-9]{1,4})\s+(.+)$/);
      const suffixNumberedMatch = rawUpper.match(/^(.+?)\s+0*([0-9]{1,4})$/)
        || cleanedToken.match(/^(.+?)\s+0*([0-9]{1,4})$/);
      const precinctNumber = prefixNumberedMatch?.[1] || suffixNumberedMatch?.[2] || '';
      if (!precinctNumber) continue;
      const resolved = resolvePrecinctKeys(`${countyNorm} - ${precinctNumber}`, resolvers);
      if (!resolved.basis || !resolved.keys.length) continue;
      const aliasNames = new Set();
      if (prefixNumberedMatch?.[2]) {
        aliasNames.add(prefixNumberedMatch[2]);
      }
      if (suffixNumberedMatch?.[1]) {
        const stem = suffixNumberedMatch[1];
        aliasNames.add(`${stem} ${Number(precinctNumber)}`);
        aliasNames.add(`${stem} ${String(Number(precinctNumber)).padStart(2, '0')}`);
        aliasNames.add(`${stem} ${String(Number(precinctNumber)).padStart(3, '0')}`);
      }
      if (cleanedToken && cleanedToken !== rawUpper) {
        aliasNames.add(cleanedToken);
      }
      if (!aliasNames.size) continue;
      for (const precinctKey of resolved.keys) {
        for (const aliasName of aliasNames) {
          addAliasVariants(resolvers[resolved.basis], countyNorm, aliasName, precinctKey);
        }
      }
    }
  }
}

function buildSingleDistrictByCounty(crosswalk, countyByPrecinct) {
  const districtsByCounty = new Map();
  for (const [precinctKey, links] of crosswalk.byPrecinct.entries()) {
    const countyNorm = countyByPrecinct.get(precinctKey);
    if (!countyNorm) continue;
    if (!districtsByCounty.has(countyNorm)) districtsByCounty.set(countyNorm, new Set());
    for (const link of links || []) {
      const districtNum = Number(link.districtNum);
      const weight = Number(link.weight);
      if (Number.isFinite(districtNum) && Number.isFinite(weight) && weight > 0.001) {
        districtsByCounty.get(countyNorm).add(districtNum);
      }
    }
  }

  const out = new Map();
  for (const [countyNorm, districtSet] of districtsByCounty.entries()) {
    if (districtSet.size === 1) out.set(countyNorm, Array.from(districtSet)[0]);
  }
  return out;
}

function buildUniqueCongressionalByLegislativeDistrict(stateHouseCrosswalk, congressionalCrosswalk) {
  const byLegDistrict = new Map();
  for (const [precinctKey, stateHouseLinks] of stateHouseCrosswalk.byPrecinct.entries()) {
    const houseMatch = (stateHouseLinks || []).find((link) => Number(link.weight) > 0.001);
    if (!houseMatch) continue;
    const legDistrict = Number(houseMatch.districtNum);
    if (!Number.isFinite(legDistrict) || legDistrict <= 0) continue;
    if (!byLegDistrict.has(legDistrict)) byLegDistrict.set(legDistrict, new Set());
    for (const link of congressionalCrosswalk.byPrecinct.get(precinctKey) || []) {
      const districtNum = Number(link.districtNum);
      const weight = Number(link.weight);
      if (Number.isFinite(districtNum) && Number.isFinite(weight) && weight > 0.001) {
        byLegDistrict.get(legDistrict).add(districtNum);
      }
    }
  }

  const out = new Map();
  for (const [legDistrict, districtSet] of byLegDistrict.entries()) {
    if (districtSet.size === 1) out.set(legDistrict, Array.from(districtSet)[0]);
  }
  return out;
}

function loadCrosswalkPair(scope, countyByPrecinct) {
  const spec = CROSSWALKS[scope];
  const loadOne = (csvPath) => {
    const rows = parseCsv(fs.readFileSync(csvPath, 'utf8'));
    const byPrecinct = new Map();
    const districts = new Set();
    for (const row of rows) {
      const precinctKey = clean(row.precinct_key || row.precinct || '');
      const districtNum = Number(row.district_num);
      const weight = Number(row.population_weight || row.area_weight || 0);
      if (!precinctKey || !Number.isFinite(districtNum) || !Number.isFinite(weight) || weight <= 0) continue;
      if (!byPrecinct.has(precinctKey)) byPrecinct.set(precinctKey, []);
      byPrecinct.get(precinctKey).push({ districtNum, weight });
      districts.add(districtNum);
    }
    return { byPrecinct, districtCount: districts.size };
  };

  const modern = loadOne(spec.modern);
  const legacy = loadOne(spec.legacy);
  return {
    modern,
    legacy,
    districtCount: modern.districtCount || legacy.districtCount,
    singleDistrictByCounty: buildSingleDistrictByCounty(modern, countyByPrecinct),
  };
}

function loadSourceManifest() {
  return readJson(path.join(CONTESTS_DIR, 'manifest.json'));
}

function loadManifest(filePath) {
  if (!fs.existsSync(filePath)) return { files: [] };
  return readJson(filePath);
}

function isPrecinctContestPayload(payload) {
  return Array.isArray(payload?.rows) && payload.rows.length > 0;
}

function isContestedPrecinctPayload(payload) {
  const candidateCount = Number(payload?.meta?.candidate_count);
  if (Number.isFinite(candidateCount)) {
    return candidateCount >= 2;
  }
  let dem = 0;
  let rep = 0;
  let other = 0;
  for (const row of payload?.rows || []) {
    dem += Number(row?.dem_votes) || 0;
    rep += Number(row?.rep_votes) || 0;
    other += Number(row?.other_votes) || 0;
  }
  let nonzeroBuckets = 0;
  if (dem > 0) nonzeroBuckets += 1;
  if (rep > 0) nonzeroBuckets += 1;
  if (other > 0) nonzeroBuckets += 1;
  return nonzeroBuckets >= 2;
}

function resolvePrecinctKeys(rowCounty, resolvers) {
  const normalized = normalizeCountyToken(rowCounty);
  if (!normalized.includes(' - ')) {
    return { basis: null, keys: [] };
  }

  const [countyNorm, rawToken] = normalized.split(' - ', 2);
  const modernCountyMap = resolvers.modern.get(countyNorm);
  const legacyCountyMap = resolvers.legacy.get(countyNorm);
  const modernHits = new Set();
  const legacyHits = new Set();
  const aliasCandidates = new Set([upper(rawToken)]);
  const cleanedToken = upper(rawToken)
    .replace(/[#.]/g, ' ')
    .replace(/\s*-\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (cleanedToken) aliasCandidates.add(cleanedToken);

  if (/^\d+$/.test(rawToken)) {
    for (const variant of buildNumericVariants(rawToken)) aliasCandidates.add(variant);
  }
  const leadingNumeric = upper(rawToken).match(/^0*([0-9]{1,4})\b/);
  if (leadingNumeric) {
    for (const variant of buildNumericVariants(leadingNumeric[1])) aliasCandidates.add(variant);
  }
  const cleanedLeadingName = cleanedToken.replace(/^0*[0-9]{1,4}\s+/, '').trim();
  if (cleanedLeadingName) {
    aliasCandidates.add(cleanedLeadingName);
    for (const variant of directionalNameVariants(cleanedLeadingName)) aliasCandidates.add(variant);
  }
  const trailingNumeric = cleanedToken.match(/(?:^| )0*([0-9]{1,4})$/);
  if (trailingNumeric) {
    for (const variant of buildNumericVariants(trailingNumeric[1])) aliasCandidates.add(variant);
    const stem = cleanedToken.replace(/(?:^| )0*[0-9]{1,4}$/, '').trim();
    if (stem) {
      aliasCandidates.add(`${stem} ${Number(trailingNumeric[1])}`);
      aliasCandidates.add(`${stem} ${String(Number(trailingNumeric[1])).padStart(2, '0')}`);
      aliasCandidates.add(`${stem} ${String(Number(trailingNumeric[1])).padStart(3, '0')}`);
    }
  }
  const trailingName = upper(rawToken).replace(/^0*[0-9]{1,4}\s+/, '').trim();
  if (trailingName) {
    aliasCandidates.add(trailingName);
    for (const variant of directionalNameVariants(trailingName)) aliasCandidates.add(variant);
  }
  for (const variant of directionalNameVariants(cleanedToken)) aliasCandidates.add(variant);
  for (const variant of directionalNameVariants(rawToken)) aliasCandidates.add(variant);

  for (const alias of aliasCandidates) {
    const modernKeys = modernCountyMap?.get(alias);
    if (modernKeys) {
      for (const key of modernKeys) modernHits.add(key);
    }
    const legacyKeys = legacyCountyMap?.get(alias);
    if (legacyKeys) {
      for (const key of legacyKeys) legacyHits.add(key);
    }
  }

  const hasLetters = /[A-Z]/.test(rawToken);
  if (hasLetters && modernHits.size === 1) return { basis: 'modern', keys: Array.from(modernHits) };
  if (!hasLetters && legacyHits.size === 1) return { basis: 'legacy', keys: Array.from(legacyHits) };
  if (modernHits.size === 1 && legacyHits.size !== 1) return { basis: 'modern', keys: Array.from(modernHits) };
  if (legacyHits.size === 1 && modernHits.size !== 1) return { basis: 'legacy', keys: Array.from(legacyHits) };
  if (modernHits.size > 0 && legacyHits.size === 0) return { basis: 'modern', keys: Array.from(modernHits) };
  if (legacyHits.size > 0 && modernHits.size === 0) return { basis: 'legacy', keys: Array.from(legacyHits) };
  return { basis: null, keys: [] };
}

function buildDirect2022Links(rowLabel, year, scope, legislative2022Resolver, congressional2022Resolver) {
  if (Number(year) !== 2022) return [];
  const normalized = normalizeCountyToken(rowLabel);
  if (!normalized.includes(' - ')) return [];
  const [countyNorm, rawToken] = normalized.split(' - ', 2);
  const token = upper(rawToken);

  if (token.includes('CO TOTAL')) return [];

  if (scope === 'congressional') {
    const workbookDistrict = congressional2022Resolver?.get(countyNorm)?.get(token);
    if (Number.isFinite(workbookDistrict) && workbookDistrict > 0) {
      return [{ districtNum: workbookDistrict, weight: 1 }];
    }
    if (countyNorm === 'KOOTENAI' || countyNorm === 'CANYON') {
      return [{ districtNum: 1, weight: 1 }];
    }
    if (countyNorm === 'MADISON') {
      return [{ districtNum: 2, weight: 1 }];
    }
    if (countyNorm === 'GOODING') {
      return [{ districtNum: 2, weight: 1 }];
    }
    return [];
  }

  if (scope !== 'state_house' && scope !== 'state_senate') return [];

  const workbookDistrict = legislative2022Resolver?.get(countyNorm)?.get(token);
  if (Number.isFinite(workbookDistrict) && workbookDistrict > 0) {
    return [{ districtNum: workbookDistrict, weight: 1 }];
  }

  if (countyNorm === 'KOOTENAI') {
    const match = upper(rawToken).match(/^([2-5])[0-9]{2}$/);
    if (!match) return [];
    return [{ districtNum: Number(match[1]), weight: 1 }];
  }

  if (countyNorm === 'CANYON') {
    const digits = upper(rawToken).match(/^([0-9]{2})([0-9]{2})/);
    if (!digits) return [];
    const districtNum = Number(digits[2]);
    if (!Number.isFinite(districtNum) || districtNum <= 0) return [];
    return [{ districtNum, weight: 1 }];
  }

  if (countyNorm === 'MADISON') {
    const madisonLabels = new Set([
      '4TH SOUTH',
      '6TH SOUTH',
      'ABSENTEE',
      'ADAMS',
      'ARCHER',
      'BURTON',
      'CITY CENTER',
      'FAIRGROUNDS',
      'HIBBARD',
      'LINCOLN',
      'LYMAN',
      'MOODY',
      'PIONEER EAST',
      'PIONEER WEST',
      'PLANO',
      'POLELINE',
      'PORTER PARK',
      'REXBURG HILL',
      'SALEM',
      'SUGAR CITY',
      'TREJO',
      'UNIVERSITY',
    ]);
    if (madisonLabels.has(token)) {
      return [{ districtNum: 34, weight: 1 }];
    }
  }

  if (countyNorm === 'GOODING') {
    const goodingLabels = new Set([
      'BLISS',
      'GOODING CITY',
      'GOODING RURAL',
      'HAGERMAN',
      'WENDELL CITY',
      'WENDELL RURAL',
    ]);
    if (goodingLabels.has(token)) {
      return [{ districtNum: 24, weight: 1 }];
    }
  }

  return [];
}

function buildLegacyNumericLinks(rowLabel, year, crosswalkPair, countyFipsByName) {
  const numericYear = Number(year);
  if (!Number.isFinite(numericYear) || numericYear > 2010) return [];
  const normalized = normalizeCountyToken(rowLabel);
  if (!normalized.includes(' - ')) return [];
  const [countyNorm, rawToken] = normalized.split(' - ', 2);
  const countyFips = countyFipsByName.get(countyNorm);
  if (!countyFips) return [];

  const cleanedToken = upper(rawToken)
    .replace(/[#.]/g, ' ')
    .replace(/\s*-\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const numericMatch = cleanedToken.match(/^0*([0-9]{1,3})$/)
    || cleanedToken.match(/^0*([0-9]{1,3})\s+/)
    || cleanedToken.match(/\s+0*([0-9]{1,3})$/);
  const precinctNumber = numericMatch?.[1] || '';
  if (!precinctNumber) return [];

  const precinctKey = `16${countyFips}${countyFips}${String(Number(precinctNumber)).padStart(3, '0')}`;
  return crosswalkPair?.legacy?.byPrecinct?.get(precinctKey) || [];
}

function inferStructuredLegislativeDistrict(rowLabel) {
  const normalized = normalizeCountyToken(rowLabel);
  if (!normalized.includes(' - ')) return null;
  const [countyNorm, rawToken] = normalized.split(' - ', 2);
  const cleanedToken = upper(rawToken)
    .replace(/[#.]/g, ' ')
    .replace(/\s*-\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  let districtNum = null;
  if (countyNorm === 'ADA') {
    const match = cleanedToken.match(/^([0-9]{2})[0-9]{2}$/);
    districtNum = match ? Number(match[1]) : null;
  } else if (countyNorm === 'CANYON') {
    const match = cleanedToken.match(/^[0-9]{2}\s*([0-9]{2})$/)
      || cleanedToken.match(/^([0-9]{2})\s+([0-9]{2})$/);
    districtNum = match ? Number(match[1] || match[2]) : null;
  } else if (countyNorm === 'KOOTENAI') {
    const match = cleanedToken.match(/^PRECINCT\s+([2-5])[0-9]{2}$/);
    districtNum = match ? Number(match[1]) : null;
  } else if (countyNorm === 'BONNEVILLE') {
    const match = cleanedToken.match(/^ABSENTEE\s+([0-9]{2})$/);
    districtNum = match ? Number(match[1]) : null;
  } else if (countyNorm === 'BANNOCK') {
    const match = cleanedToken.match(/^ABSENTEE\s+L?([0-9]{2})$/);
    districtNum = match ? Number(match[1]) : null;
  }

  if (!Number.isFinite(districtNum) || districtNum <= 0 || districtNum > 35) return null;
  return districtNum;
}

function buildStructuredDirectLinks(rowLabel, scope, crosswalkPair, uniqueCongressionalByLegDistrict) {
  const normalized = normalizeCountyToken(rowLabel);
  if (!normalized.includes(' - ')) return [];
  const [countyNorm] = normalized.split(' - ', 2);

  const structuredDistrict = inferStructuredLegislativeDistrict(rowLabel);
  if (Number.isFinite(structuredDistrict)) {
    if (scope === 'state_house' || scope === 'state_senate') {
      return [{ districtNum: structuredDistrict, weight: 1 }];
    }
    if (scope === 'congressional') {
      const congressionalDistrict = uniqueCongressionalByLegDistrict.get(structuredDistrict);
      if (Number.isFinite(congressionalDistrict) && congressionalDistrict > 0) {
        return [{ districtNum: congressionalDistrict, weight: 1 }];
      }
    }
  }

  const countyDistrict = crosswalkPair?.singleDistrictByCounty?.get(countyNorm);
  if (Number.isFinite(countyDistrict) && countyDistrict > 0) {
    return [{ districtNum: countyDistrict, weight: 1 }];
  }

  return [];
}

function aggregateContestToScope(
  payload,
  manifestEntry,
  scope,
  crosswalkPair,
  resolvers,
  legislative2022Resolver,
  congressional2022Resolver,
  countyFipsByName,
  uniqueCongressionalByLegDistrict
) {
  const contestType = clean(payload.contest_type || manifestEntry?.contest_type);
  const totalsByDistrict = new Map();
  let matchedPrecinctKeys = 0;
  let totalPrecinctKeys = 0;
  let weightedVoteSum = 0;
  let statewideDemCandidate = '';
  let statewideRepCandidate = '';
  let modernMatchCount = 0;
  let legacyMatchCount = 0;
  let directMatchCount = 0;

  for (const row of payload.rows || []) {
    const rowLabel = clean(row.county);
    if (!rowLabel) continue;
    totalPrecinctKeys += 1;

    const links = [];
    let resolved = { basis: null, keys: [] };
    const preferDirect2022 = Number(payload.year || manifestEntry?.year) === 2022
      && (scope === 'state_house' || scope === 'state_senate' || scope === 'congressional');

    if (preferDirect2022) {
      for (const match of buildDirect2022Links(
        rowLabel,
        payload.year || manifestEntry?.year,
        scope,
        legislative2022Resolver,
        congressional2022Resolver
      )) {
        links.push(match);
      }
    }

    if (!links.length) {
      for (const match of buildLegacyNumericLinks(
        rowLabel,
        payload.year || manifestEntry?.year,
        crosswalkPair,
        countyFipsByName
      )) {
        links.push(match);
      }
    }

    if (!links.length) {
      for (const match of buildStructuredDirectLinks(
        rowLabel,
        scope,
        crosswalkPair,
        uniqueCongressionalByLegDistrict
      )) {
        links.push(match);
      }
    }

    if (!links.length) {
      resolved = resolvePrecinctKeys(rowLabel, resolvers);
      if (resolved.keys.length && resolved.basis) {
        const crosswalk = crosswalkPair[resolved.basis];
        for (const precinctKey of resolved.keys) {
          const matches = crosswalk.byPrecinct.get(precinctKey) || [];
          for (const match of matches) links.push(match);
        }
      }
    }
    if (!links.length && !preferDirect2022) {
      for (const match of buildDirect2022Links(
        rowLabel,
        payload.year || manifestEntry?.year,
        scope,
        legislative2022Resolver,
        congressional2022Resolver
      )) {
        links.push(match);
      }
    }
    if (!links.length) continue;

    const demVotes = Number(row.dem_votes) || 0;
    const repVotes = Number(row.rep_votes) || 0;
    const otherVotes = Number(row.other_votes) || 0;
    const totalVotes = Number(row.total_votes) || (demVotes + repVotes + otherVotes);
    if (totalVotes <= 0) continue;

    matchedPrecinctKeys += 1;
    if (resolved.basis === 'modern') modernMatchCount += 1;
    if (resolved.basis === 'legacy') legacyMatchCount += 1;
    if (!resolved.basis) directMatchCount += 1;
    if (!statewideDemCandidate) statewideDemCandidate = clean(row.dem_candidate);
    if (!statewideRepCandidate) statewideRepCandidate = clean(row.rep_candidate);

    for (const link of links) {
      const districtNum = Number(link.districtNum);
      const weight = Number(link.weight);
      if (!Number.isFinite(districtNum) || !Number.isFinite(weight) || weight <= 0) continue;
      if (!totalsByDistrict.has(districtNum)) {
        totalsByDistrict.set(districtNum, { dem: 0, rep: 0, other: 0, total: 0 });
      }
      const bucket = totalsByDistrict.get(districtNum);
      bucket.dem += demVotes * weight;
      bucket.rep += repVotes * weight;
      bucket.other += otherVotes * weight;
      bucket.total += totalVotes * weight;
      weightedVoteSum += totalVotes * weight;
    }
  }

  const results = {};
  const districtCount = Number(crosswalkPair?.districtCount) || 0;
  const sortedDistrictNums = districtCount > 0
    ? Array.from({ length: districtCount }, (_, idx) => idx + 1)
    : Array.from(totalsByDistrict.keys()).sort((a, b) => a - b);

  for (const districtNum of sortedDistrictNums) {
    const totals = totalsByDistrict.get(districtNum) || { dem: 0, rep: 0, other: 0, total: 0 };
    const demVotes = Math.round(totals.dem);
    const repVotes = Math.round(totals.rep);
    const otherVotes = Math.round(totals.other);
    const totalVotes = Math.round(totals.total);
    const hasData = totalVotes > 0;
    const margin = repVotes - demVotes;
    const marginPct = hasData ? Number(((margin / totalVotes) * 100).toFixed(4)) : 0;
    const winner = hasData
      ? (margin > 0 ? 'REP' : (margin < 0 ? 'DEM' : 'TIE'))
      : 'TIE';
    const color = hasData ? pickColor(marginPct) : '#9ca3af';
    results[String(districtNum)] = {
      dem_votes: demVotes,
      rep_votes: repVotes,
      other_votes: otherVotes,
      total_votes: totalVotes,
      dem_candidate: statewideDemCandidate,
      rep_candidate: statewideRepCandidate,
      margin,
      margin_pct: marginPct,
      winner,
      color,
      competitiveness: { color },
      no_data: !hasData,
    };
  }

  const statewideTotal = (payload.rows || []).reduce((sum, row) => sum + (Number(row.total_votes) || 0), 0);
  const matchCoveragePct = totalPrecinctKeys ? Number(((matchedPrecinctKeys / totalPrecinctKeys) * 100).toFixed(2)) : 0;
  const voteCoveragePct = statewideTotal ? Number(((weightedVoteSum / statewideTotal) * 100).toFixed(2)) : 0;
  return {
    year: Number(payload.year || manifestEntry?.year),
    scope,
    contest_type: contestType,
    meta: {
      match_coverage_pct: matchCoveragePct,
      matched_precinct_keys: matchedPrecinctKeys,
      total_precinct_keys: totalPrecinctKeys,
      weighted_vote_coverage_pct: voteCoveragePct,
      source: 'idaho_hybrid_precinct_crosswalk_population_weighted',
      office: clean(payload?.meta?.office) || clean(manifestEntry?.office) || contestType,
      nongeo_allocation_mode: 'precinct_population_weighted',
        candidate_count: Number(payload?.meta?.candidate_count) || null,
        precinct_basis_breakdown: {
          modern_2020_vtd20_rows: modernMatchCount,
          legacy_2008_vtd00_rows: legacyMatchCount,
          direct_2022_districtcoded_rows: directMatchCount,
        },
      },
      general: { results },
    };
  }

function filterExistingEntries(manifest, scopeGuard = null) {
  const files = Array.isArray(manifest.files) ? manifest.files : [];
  return files.filter((entry) => {
    const scope = clean(entry.scope);
    const contestType = clean(entry.contest_type);
    if (scopeGuard && scope !== scopeGuard) return true;
    if (!MANAGED_SCOPES.has(scope)) return true;
    if (!MANAGED_CONTEST_TYPES.has(contestType)) return true;
    return false;
  });
}

function main() {
  const sourceManifest = loadSourceManifest();
  const countyByPrecinct = readModernCountyByPrecinctKey();
  const crosswalkPairs = Object.fromEntries(
    Object.keys(CROSSWALKS).map((scope) => [scope, loadCrosswalkPair(scope, countyByPrecinct)])
  );
  const uniqueCongressionalByLegDistrict = buildUniqueCongressionalByLegislativeDistrict(
    crosswalkPairs.state_house.modern,
    crosswalkPairs.congressional.modern
  );
  const resolvers = {
    modern: loadModernPrecinctResolver(),
    legacy: loadLegacyPrecinctResolver(),
  };
  const legislative2022Resolver = load2022LegislativeWorkbookResolver();
  const congressional2022Resolver = load2022CongressionalWorkbookResolver();
  const countyFipsByName = readCountyFipsByName();
  addContestDerivedAliasBridges(sourceManifest, resolvers);
  const manifest2024 = loadManifest(MANIFEST_2024_PATH);
  const manifest2026 = loadManifest(MANIFEST_2026_PATH);
  const new2024Entries = [];
  const new2026Entries = [];

  manifest2024.files = filterExistingEntries(manifest2024);
  manifest2026.files = filterExistingEntries(manifest2026, 'congressional');

  for (const entry of sourceManifest.files || []) {
    const contestType = clean(entry.contest_type);
    if (!MANAGED_CONTEST_TYPES.has(contestType)) continue;
    const sourcePath = path.join(CONTESTS_DIR, clean(entry.file));
    if (!fs.existsSync(sourcePath)) continue;
    const payload = readJson(sourcePath);
    const sourceYear = Number(entry.year || payload?.year);
    if (!Number.isFinite(sourceYear) || sourceYear < MIN_YEAR || sourceYear > MAX_YEAR) continue;
    if (!isPrecinctContestPayload(payload)) continue;
    if (!isContestedPrecinctPayload(payload)) continue;

    for (const scope of Object.keys(CROSSWALKS)) {
      const aggregated = aggregateContestToScope(
        payload,
        entry,
        scope,
        crosswalkPairs[scope],
        resolvers,
        legislative2022Resolver,
        congressional2022Resolver,
        countyFipsByName,
        uniqueCongressionalByLegDistrict
      );
      if (!Object.keys(aggregated.general.results || {}).length) continue;

      const fileName = `${CROSSWALKS[scope].prefix}_${contestType}_${aggregated.year}.json`;
      writeJson(path.join(OUT_2024_DIR, fileName), aggregated);
      new2024Entries.push({
        year: Number(aggregated.year),
        scope,
        contest_type: contestType,
        file: fileName,
        districts: crosswalkPairs[scope].districtCount,
        office: clean(payload?.meta?.office) || clean(entry?.office) || contestType,
      });

      if (scope === 'congressional') {
        writeJson(path.join(OUT_2026_DIR, fileName), aggregated);
        new2026Entries.push({
          year: Number(aggregated.year),
          scope,
          contest_type: contestType,
          file: fileName,
          districts: crosswalkPairs[scope].districtCount,
          office: clean(payload?.meta?.office) || clean(entry?.office) || contestType,
        });
      }
    }
  }

  manifest2024.files = manifest2024.files.concat(new2024Entries).sort((a, b) => {
    const yearDiff = Number(a.year) - Number(b.year);
    if (yearDiff) return yearDiff;
    const scopeDiff = clean(a.scope).localeCompare(clean(b.scope));
    if (scopeDiff) return scopeDiff;
    return clean(a.contest_type).localeCompare(clean(b.contest_type));
  });

  manifest2026.files = manifest2026.files.concat(new2026Entries).sort((a, b) => {
    const yearDiff = Number(a.year) - Number(b.year);
    if (yearDiff) return yearDiff;
    return clean(a.contest_type).localeCompare(clean(b.contest_type));
  });

  writeJson(MANIFEST_2024_PATH, manifest2024);
  writeJson(MANIFEST_2026_PATH, manifest2026);
  console.log(`Wrote ${new2024Entries.length} district entries to 2024-lines manifest`);
  console.log(`Wrote ${new2026Entries.length} congressional entries to 2026-lines manifest`);
}

main();
