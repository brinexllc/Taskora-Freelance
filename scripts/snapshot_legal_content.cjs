// Snapshot exactly the currently displayed legal copy. This does not approve it.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const names = ['mvp-copy.js', 'catalog-copy.js', 'design-copy.js', 'audit-copy.js', 'i18n.js'];
const source = names.map(name => fs.readFileSync(path.join(root, 'frontend/lib', name), 'utf8')
  .replace(/^import .+;\r?\n/gm, '').replace(/export /g, '')).join('\n');
const dictionaries = new Function(source + '\nreturn dictionaries;')();
const languages = Object.fromEntries(Object.entries(dictionaries).map(([lang, d]) => [lang, {
  terms: d.termsBody, privacy: d.privacyBody,
  how_it_works: [d.step1, d.step2, d.step3], fees: d.feeTerms,
  support_guidance: d.supportGuidance, notice: d.legalNotice,
}]));
const manifest = {version: 'mvp-published-copy-2026-09-13', approved: false,
  provenance: 'Snapshot of the existing legal-page.jsx copy; no legal/operator approval supplied.',
  operator: {}, support: {}, languages};
fs.writeFileSync(path.join(root, 'backend/marketplace/legal_content.json'), JSON.stringify(manifest, null, 2) + '\n');
