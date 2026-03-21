#!/usr/bin/env bash
# readability.sh - Mozilla Readability AEO score
# Input: URL or file path
# Output: aeo_score: N (0-100)
# No Chrome required

set -euo pipefail

TARGET="$1"

bun -e "
const { JSDOM } = require('jsdom');
const { Readability, isProbablyReaderable } = require('@mozilla/readability');
const fs = require('fs');

async function evaluate(target) {
  let html, url;
  if (target.startsWith('http://') || target.startsWith('https://')) {
    const res = await fetch(target);
    html = await res.text();
    url = target;
  } else {
    const path = require('path').resolve(target);
    html = fs.readFileSync(path, 'utf-8');
    url = 'file://' + path;
  }

  const dom = new JSDOM(html, { url });
  const doc = dom.window.document;
  const extractable = isProbablyReaderable(doc);
  const reader = new Readability(doc.cloneNode(true));
  const parsed = reader.parse();

  let metaScore = 0;
  if (parsed?.title) metaScore += 10;
  if (parsed?.excerpt) metaScore += 5;
  if (parsed?.byline) metaScore += 5;
  if (parsed?.publishedTime) metaScore += 5;
  if (parsed?.lang) metaScore += 5;

  let structScore = 0;
  const len = parsed?.length ?? 0;
  if (len >= 2000) structScore = 40;
  else if (len >= 1000) structScore = 30;
  else if (len >= 500) structScore = 20;
  else if (len >= 200) structScore = 10;
  else if (len > 0) structScore = 5;

  const extractScore = (extractable && parsed) ? 30 : 0;
  const aeo = Math.min(100, metaScore + structScore + extractScore);

  console.log('aeo_score: ' + aeo);
}

evaluate('$TARGET').catch(e => {
  console.error(e.message);
  console.log('aeo_score: 0');
});
" 2>/dev/null
