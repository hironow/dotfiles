#!/usr/bin/env bash
# completeness.sh - Placeholder detection and completeness score
# Input: file path (HTML)
# Output: completeness_score: N (0-100)
# No Chrome required

set -euo pipefail

TARGET="$1"

bun -e "
const cheerio = require('cheerio');
const fs = require('fs');

let html;
if ('$TARGET'.startsWith('http://') || '$TARGET'.startsWith('https://')) {
  console.error('completeness.sh requires a file path, not URL');
  console.log('completeness_score: 0');
  process.exit(0);
}
html = fs.readFileSync('$TARGET', 'utf-8');
const \$ = cheerio.load(html);

let placeholders = 0;
let nonFunctional = 0;
let a11yGaps = 0;

// Placeholder text patterns
const patterns = [/lorem ipsum/i, /TODO/i, /placeholder/i, /サンプル/, /ダミー/, /〇〇/];
\$('p, span, h1, h2, h3, h4, h5, h6, li').each((_, el) => {
  const text = \$(el).text();
  for (const p of patterns) {
    if (p.test(text)) { placeholders++; break; }
  }
});

// Placeholder links
\$('a').each((_, el) => {
  const href = \$(el).attr('href') || '';
  if (href === '#' || href === '' || href === 'javascript:void(0)') {
    if (!(href === '#' && false)) placeholders++;
  }
});

// Images without src
\$('img').each((_, el) => {
  const src = \$(el).attr('src') || '';
  if (!src || src === '#' || src.startsWith('data:image/svg+xml')) placeholders++;
});

// Non-functional forms
\$('form').each((_, el) => {
  const action = \$(el).attr('action') || '';
  if (action === '' || action === '#') nonFunctional++;
});

// Missing alt text
\$('img').each((_, el) => {
  if (\$(el).attr('alt') === undefined) a11yGaps++;
});

const score = Math.max(0, 100 - placeholders * 5 - nonFunctional * 10 - a11yGaps * 3);
console.log('completeness_score: ' + score);
" 2>/dev/null
