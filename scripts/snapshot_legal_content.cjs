// Snapshot exactly the currently displayed legal copy. This does not approve it.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const target = path.join(root, 'backend/marketplace/legal_content.json');
const existing = fs.existsSync(target) ? JSON.parse(fs.readFileSync(target, 'utf8')) : {};
const version = process.argv[2];
if (!version || version === existing.version) throw new Error('Pass a new legal revision as the first argument. Owner details are preserved; approval is reset.');
const names = ['mvp-copy.js', 'catalog-copy.js', 'design-copy.js', 'audit-copy.js', 'i18n.js'];
const source = names.map(name => fs.readFileSync(path.join(root, 'frontend/lib', name), 'utf8')
  .replace(/^import .+;\r?\n/gm, '').replace(/export /g, '')).join('\n');
const dictionaries = new Function(source + '\nreturn dictionaries;')();
const languages = Object.fromEntries(Object.entries(dictionaries).map(([lang, d]) => [lang, {
  terms: d.termsBody, privacy: d.privacyBody,
  how_it_works: [d.step1, d.step2, d.step3], fees: d.feeTerms,
  support_guidance: d.supportGuidance, notice: d.legalNotice,
}]));
const manifest = {version, approved: false,
  provenance: 'Snapshot of current translated legal copy. Previously supplied owner details preserved; this revised document requires approval.',
  operator: existing.operator || {}, support: existing.support || {}, languages};
fs.writeFileSync(target, JSON.stringify(manifest, null, 2) + '\n');
