#!/usr/bin/env bash
# Blog article quality evaluator
# Outputs: score:<number> (0-100, higher is better)
#
# Dimensions:
#   1. Freshness (25pts) - references to specific versions, dates, commit hashes
#   2. Anti-tutorial (25pts) - penalize tutorial patterns, reward analysis
#   3. Factual density (25pts) - concrete references, links, tables, code
#   4. Depth & insight (25pts) - word count, section structure, original analysis

set -uo pipefail

BLOG_DIR="${1:-autoblogs}"
CHANGELOG="docs/changelogs.md"

# Helper: count grep matches safely (returns 0 on no match)
count_matches() {
    local pattern="$1"
    local flags="${2:--oE}"
    # `grep -c` is not equivalent here: with -o flag we want occurrence count
    # (potentially multiple per line), not matching-line count.
    # shellcheck disable=SC2126,SC2086
    grep $flags "$pattern" | wc -l | tr -d ' '
}

total_score=0
article_count=0

for article in "$BLOG_DIR"/*.md; do
    [ -f "$article" ] || continue
    article_count=$((article_count + 1))

    content=$(cat "$article")
    bname=$(basename "$article")

    # ========== 1. Freshness (25pts) ==========
    freshness=0

    # Version references (v0.x.x, v1.x.x or v0.x patterns)
    version_refs=$(echo "$content" | { grep -oE 'v[0-9]+\.[0-9]+(\.[0-9]+)?' || true; } | sort -u | wc -l | tr -d ' ')
    if [ "$version_refs" -ge 8 ]; then freshness=$((freshness + 10))
    elif [ "$version_refs" -ge 4 ]; then freshness=$((freshness + 7))
    elif [ "$version_refs" -ge 2 ]; then freshness=$((freshness + 4))
    fi

    # Date references (2026-xx-xx)
    date_refs=$(echo "$content" | { grep -oE '2026-[0-9]{2}-[0-9]{2}' || true; } | wc -l | tr -d ' ')
    if [ "$date_refs" -ge 3 ]; then freshness=$((freshness + 8))
    elif [ "$date_refs" -ge 1 ]; then freshness=$((freshness + 4))
    fi

    # Cross-reference with changelog
    changelog_matches=0
    versions_in_article=$(echo "$content" | { grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || true; } | sort -u | head -10)
    if [ -n "$versions_in_article" ]; then
        while IFS= read -r version; do
            [ -z "$version" ] && continue
            if grep -qF "$version" "$CHANGELOG" 2>/dev/null; then
                changelog_matches=$((changelog_matches + 1))
            fi
        done <<< "$versions_in_article"
    fi
    if [ "$changelog_matches" -ge 5 ]; then freshness=$((freshness + 7))
    elif [ "$changelog_matches" -ge 2 ]; then freshness=$((freshness + 4))
    fi

    # ========== 2. Anti-tutorial (25pts) ==========
    anti_tutorial=25

    tutorial_phrases=(
        "まず.*インストール"
        "ステップ[0-9]"
        "手順[0-9]"
        "次に.*します"
        "Let's start"
        "First, install"
        "Step [0-9]"
        "In this tutorial"
        "Getting started"
        "Prerequisites"
        "npm install"
        "pip install"
        "mkdir"
    )
    for phrase in "${tutorial_phrases[@]}"; do
        matches=$(echo "$content" | grep -ci "$phrase" 2>/dev/null || true)
        matches=${matches:-0}
        matches=$(echo "$matches" | tr -d '[:space:]')
        [ -z "$matches" ] && matches=0
        if [ "$matches" -gt 0 ]; then
            penalty=$((matches * 3))
            anti_tutorial=$((anti_tutorial - penalty))
        fi
    done

    analysis_phrases=(
        "設計思想"
        "アーキテクチャ"
        "破壊的変更"
        "移行"
        "方向性"
        "哲学"
        "整理すると"
        "意味する"
        "示している"
        "進化"
        "成熟"
        "実用段階"
    )
    analysis_count=0
    for phrase in "${analysis_phrases[@]}"; do
        matches=$(echo "$content" | grep -c "$phrase" 2>/dev/null || true)
        matches=${matches:-0}
        matches=$(echo "$matches" | tr -d '[:space:]')
        [ -z "$matches" ] && matches=0
        analysis_count=$((analysis_count + matches))
    done
    if [ "$analysis_count" -gt 10 ]; then
        analysis_bonus=5
    else
        analysis_bonus=$((analysis_count / 2))
    fi
    anti_tutorial=$((anti_tutorial + analysis_bonus))

    [ "$anti_tutorial" -lt 0 ] && anti_tutorial=0
    [ "$anti_tutorial" -gt 25 ] && anti_tutorial=25

    # ========== 3. Factual density (25pts) ==========
    factual=0

    issue_refs=$(echo "$content" | { grep -oE '#[0-9]{2,}' || true; } | wc -l | tr -d ' ')
    if [ "$issue_refs" -ge 8 ]; then factual=$((factual + 8))
    elif [ "$issue_refs" -ge 3 ]; then factual=$((factual + 5))
    elif [ "$issue_refs" -ge 1 ]; then factual=$((factual + 2))
    fi

    table_count=$(echo "$content" | grep -c '^|' || true)
    table_count=$(echo "${table_count:-0}" | tr -d '[:space:]')
    [ -z "$table_count" ] && table_count=0
    if [ "$table_count" -ge 6 ]; then factual=$((factual + 7))
    elif [ "$table_count" -ge 3 ]; then factual=$((factual + 4))
    fi

    link_count=$(echo "$content" | { grep -oE '\[.+\]\(https?://.+\)' || true; } | wc -l | tr -d ' ')
    if [ "$link_count" -ge 3 ]; then factual=$((factual + 5))
    elif [ "$link_count" -ge 1 ]; then factual=$((factual + 3))
    fi

    code_blocks=$(echo "$content" | grep -c '```' || true)
    code_blocks=$(echo "${code_blocks:-0}" | tr -d '[:space:]')
    [ -z "$code_blocks" ] && code_blocks=0
    code_blocks=$((code_blocks / 2))
    if [ "$code_blocks" -ge 2 ]; then factual=$((factual + 5))
    elif [ "$code_blocks" -ge 1 ]; then factual=$((factual + 3))
    fi

    # ========== 4. Depth & Insight (25pts) ==========
    depth=0

    char_count=$(echo "$content" | wc -m | tr -d ' ')
    if [ "$char_count" -ge 4000 ]; then depth=$((depth + 8))
    elif [ "$char_count" -ge 2500 ]; then depth=$((depth + 5))
    elif [ "$char_count" -ge 1500 ]; then depth=$((depth + 3))
    fi

    h2_count=$(echo "$content" | grep -c '^## ' || true)
    h2_count=$(echo "${h2_count:-0}" | tr -d '[:space:]')
    [ -z "$h2_count" ] && h2_count=0
    h3_count=$(echo "$content" | grep -c '^### ' || true)
    h3_count=$(echo "${h3_count:-0}" | tr -d '[:space:]')
    [ -z "$h3_count" ] && h3_count=0
    heading_total=$((h2_count + h3_count))
    if [ "$heading_total" -ge 8 ]; then depth=$((depth + 7))
    elif [ "$heading_total" -ge 5 ]; then depth=$((depth + 5))
    elif [ "$heading_total" -ge 3 ]; then depth=$((depth + 3))
    fi

    if echo "$content" | grep -q '^## まとめ'; then
        depth=$((depth + 3))
    fi

    bold_count=$(echo "$content" | { grep -oE '\*\*[^*]+\*\*' || true; } | wc -l | tr -d ' ')
    if [ "$bold_count" -ge 10 ]; then depth=$((depth + 4))
    elif [ "$bold_count" -ge 5 ]; then depth=$((depth + 2))
    fi

    if [ "$char_count" -lt 1000 ]; then
        depth=$((depth - 5))
    fi
    [ "$depth" -lt 0 ] && depth=0
    [ "$depth" -gt 25 ] && depth=25

    # ========== Article Score ==========
    article_score=$((freshness + anti_tutorial + factual + depth))
    total_score=$((total_score + article_score))

    echo "article:${bname} freshness:${freshness} anti_tutorial:${anti_tutorial} factual:${factual} depth:${depth} total:${article_score}" >&2
done

if [ "$article_count" -eq 0 ]; then
    echo "score:0"
    exit 1
fi

avg_score=$((total_score / article_count))
echo "score:${avg_score}"
