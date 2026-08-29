const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const GENERATED_DIRS = [
  path.join(ROOT, 'data', 'contests'),
  path.join(ROOT, 'data', 'district_contests'),
  path.join(ROOT, 'data', 'district_contests_2022_lines'),
  path.join(ROOT, 'data', 'district_contests_2026_lines'),
];

function jsonFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) return jsonFiles(entryPath);
    return entry.isFile() && entry.name.toLowerCase().endsWith('.json') ? [entryPath] : [];
  });
}

let updated = 0;
for (const filePath of GENERATED_DIRS.flatMap(jsonFiles)) {
  const original = fs.readFileSync(filePath, 'utf8');
  const normalized = original.replace(/C\.?\s*L\.?\s+(?:\\"|')Butch(?:\\"|')\s+Otter/gi, 'Butch Otter');
  if (normalized === original) continue;
  fs.writeFileSync(filePath, normalized, 'utf8');
  updated += 1;
  console.log(`Updated ${path.relative(ROOT, filePath)}`);
}
console.log(`Normalized candidate names in ${updated} generated files`);
