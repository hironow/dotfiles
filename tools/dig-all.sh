#!/bin/bash

# ==============================================================================
# Script Name: dig-all.sh
# Description: Display all DNS records for a domain in a clean, colorful format.
#              Optionally compare results across multiple public DNS servers.
# Usage:       ./dig-all.sh [OPTIONS] <domain>
# ==============================================================================

set -eo pipefail

# --- Colors (short names) ---
R='\033[0;31m'  G='\033[0;32m'  Y='\033[1;33m'
BL='\033[0;34m' C='\033[0;36m'  B='\033[1m'  N='\033[0m'

# --- Public DNS Servers (format: "name:ip") ---
DNS_SERVERS=(
    "Google:8.8.8.8"
    "Cloudflare:1.1.1.1"
    "Quad9:9.9.9.9"
)

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] <domain>

Display all DNS records for a domain.

OPTIONS:
  -c, --compare    Compare results across multiple public DNS servers
                   (Google 8.8.8.8, Cloudflare 1.1.1.1, Quad9 9.9.9.9)
  -h, --help       Show this help message

EXAMPLES:
  $(basename "$0") example.com
  $(basename "$0") --compare example.com
EOF
}

format_ttl() {
    local seconds=$1
    [[ ! "$seconds" =~ ^[0-9]+$ ]] && { echo "$seconds"; return; }
    if (( seconds >= 86400 )); then echo "$((seconds / 86400))d"
    elif (( seconds >= 3600 )); then echo "$((seconds / 3600))h"
    elif (( seconds >= 60 )); then echo "$((seconds / 60))m"
    else echo "${seconds}s"
    fi
}

lookup_records() {
    local domain=$1 server=${2:-""} server_label=${3:-""}

    local -a dig_opts=()
    [[ -n "$server" ]] && dig_opts+=("@${server}")

    if [[ -n "$server_label" ]]; then
        echo -e "${B}----------------------------------------${N}"
        echo -e " DNS Server: ${C}${server_label}${N} (${server})"
        echo -e "${B}----------------------------------------${N}"
    fi

    printf "${C}%-5s${N} | %-30s | %-6s | %s\n" "TYPE" "NAME" "TTL" "VALUE"
    echo "------------------------------------------------------------------------"

    local record_types=("A" "AAAA" "CNAME" "MX" "TXT" "NS" "SOA")

    for type in "${record_types[@]}"; do
        local output
        output=$(dig +noall +answer "${dig_opts[@]}" "$domain" "$type" 2>/dev/null | grep -v '^;' | grep -v '^$' | sed 's/\.	/	/' | sed 's/	IN	/	/' || true)

        if [[ -n "$output" ]]; then
            echo "$output" | while read -r line; do
                local name ttl rec_type value
                name=$(echo "$line" | awk '{print $1}')
                ttl=$(echo "$line" | awk '{print $2}')
                rec_type=$(echo "$line" | awk '{print $3}')
                value=$(echo "$line" | awk '{$1=$2=$3=""; sub(/^[ \t]+/, ""); print}')
                printf "${BL}%-5s${N} | %-30s | %-6s | %s\n" "$rec_type" "$name" "$(format_ttl "$ttl")" "$value"
            done
        fi
    done
    echo ""
}

compare_records() {
    local domain=$1

    echo -e "${B}========================================${N}"
    echo -e " DNS Comparison for: ${G}${domain}${N}"
    echo -e "${B}========================================${N}"
    echo ""

    local first_value="" has_diff=0 results=()

    for entry in "${DNS_SERVERS[@]}"; do
        local name="${entry%%:*}" server="${entry##*:}"
        local value
        value=$(dig "@${server}" "$domain" A +short 2>/dev/null | sort | tr '\n' ',' | sed 's/,$//')
        results+=("${name}:${server}:${value}")

        if [[ -z "$first_value" ]]; then
            first_value="$value"
        elif [[ "$value" != "$first_value" ]]; then
            has_diff=1
        fi
    done

    echo -e "${B}A Record Comparison:${N}"
    for result in "${results[@]}"; do
        local name="${result%%:*}"
        local rest="${result#*:}"
        local server="${rest%%:*}"
        local value="${rest#*:}"
        if [[ -z "$value" ]]; then
            printf "  %-12s (%s): ${Y}(no record)${N}\n" "$name" "$server"
        else
            printf "  %-12s (%s): %s\n" "$name" "$server" "$value"
        fi
    done

    if (( has_diff )); then
        echo -e "\n${Y}WARNING: A records differ between DNS servers!${N}"
        echo "This may indicate DNS propagation in progress."
    else
        echo -e "\n${G}OK: A records are consistent across all servers.${N}"
    fi

    echo ""
    echo -e "${B}========================================${N}"
    echo -e " Detailed Records (using system resolver)"
    echo -e "${B}========================================${N}"
    echo ""

    lookup_records "$domain"
}

# --- Main ---

if ! command -v dig &> /dev/null; then
    echo -e "${R}Error: 'dig' command not found.${N}"
    echo "Install: brew install bind (macOS) or apt install dnsutils (Linux)"
    exit 1
fi

COMPARE_MODE=0 DOMAIN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--compare) COMPARE_MODE=1; shift ;;
        -h|--help) show_help; exit 0 ;;
        -*) echo -e "${R}Error: Unknown option: $1${N}"; show_help; exit 1 ;;
        *) DOMAIN="$1"; shift ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then
    echo -e "${R}Error: Domain is required.${N}"
    show_help
    exit 1
fi

show_guide() {
    echo -e "${B}📖 レコードの読み方${N}"
    echo "────────────────────────────────────────"
    echo -e "  ${BL}A${N}     : サーバーの IPv4 アドレス（Webサイトの場所）"
    echo -e "  ${BL}AAAA${N}  : サーバーの IPv6 アドレス（新しい形式のIP）"
    echo -e "  ${BL}CNAME${N} : 別名（このドメインは実は○○を指している）"
    echo -e "  ${BL}MX${N}    : メールサーバー（メールの届け先）"
    echo -e "  ${BL}TXT${N}   : テキスト情報（認証・検証用、SPFなど）"
    echo -e "  ${BL}NS${N}    : ネームサーバー（このドメインを管理しているDNS）"
    echo -e "  ${BL}SOA${N}   : 権威情報（ゾーンの管理者情報）"
    echo ""
    echo -e "${B}📊 TTL（Time To Live）について${N}"
    echo "────────────────────────────────────────"
    echo "  TTL はキャッシュ保持時間です。"
    echo "  - 短い (5m以下): 頻繁に変更される設定、または移行中"
    echo "  - 中程度 (1h): 一般的な設定"
    echo "  - 長い (6h以上): 安定した設定、変更予定なし"
    echo ""
}

if (( COMPARE_MODE )); then
    compare_records "$DOMAIN"
    echo -e "${B}💡 比較結果の見方${N}"
    echo "────────────────────────────────────────"
    echo -e "  ${G}OK${N} : 全サーバーで同じ値 → 正常に伝播済み"
    echo -e "  ${Y}WARNING${N} : 値が異なる → DNS変更が伝播中、または設定ミス"
    echo ""
    echo "  値が異なる場合、数時間〜48時間待つと同期されます。"
    echo "  それでも異なる場合は、DNS設定を確認してください。"
    echo ""
    show_guide
else
    echo -e "${B}========================================${N}"
    echo -e " DNS Records for: ${G}${DOMAIN}${N}"
    echo -e "${B}========================================${N}"
    echo ""
    lookup_records "$DOMAIN"
    show_guide
fi
