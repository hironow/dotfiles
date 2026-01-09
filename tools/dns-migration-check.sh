#!/bin/bash

# ==============================================================================
# Script Name: dns-migration-check.sh
# Description: Safely verifies DNS migration by comparing active records against
#              ALL nameservers of the target zone to ensure consistency.
#              Also supports propagation checking across global DNS servers.
# Usage:       ./dns-migration-check.sh [OPTIONS] <domain> [target_ns_hint]
# ==============================================================================

set -eo pipefail

# --- Colors (short names) ---
R='\033[0;31m'  G='\033[0;32m'  Y='\033[1;33m'
C='\033[0;36m'  B='\033[1m'     N='\033[0m'

# --- Public DNS Servers (format: "name:ip") ---
PUBLIC_DNS=(
    "Google:8.8.8.8"
    "Cloudflare:1.1.1.1"
    "OpenDNS:208.67.222.222"
    "Quad9:9.9.9.9"
)

show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] <domain> [target_ns_hint]

Safely verify DNS migration or check propagation status.

MODES:
  Migration Check (default):
    $(basename "$0") <domain> <target_ns_hint>
    Compare live DNS against target nameserver records.

  Propagation Check:
    $(basename "$0") -p <domain>
    Check if DNS records are consistent across global DNS servers.

OPTIONS:
  -p, --propagation    Check propagation across public DNS servers
  -h, --help           Show this help message

EXAMPLES:
  $(basename "$0") example.com ns-cloud-a1.googledomains.com
  $(basename "$0") --propagation example.com
EOF
}

check_propagation() {
    local domain=$1

    echo -e "${B}==============================================================${N}"
    echo -e " DNS Propagation Check: ${C}${domain}${N}"
    echo -e "${B}==============================================================${N}"
    echo ""

    local record_types=("A" "AAAA" "MX" "NS")
    local global_ok=1

    for type in "${record_types[@]}"; do
        echo -e "${B}--- ${type} Record ---${N}"

        local first_value="" has_diff=0 results=()

        for entry in "${PUBLIC_DNS[@]}"; do
            local name="${entry%%:*}" server="${entry##*:}"
            local value
            value=$(dig "@${server}" "$domain" "$type" +short 2>/dev/null | sort | tr '\n' ',' | sed 's/,$//')
            results+=("${name}:${server}:${value}")

            if [[ -z "$first_value" ]]; then
                first_value="$value"
            elif [[ "$value" != "$first_value" ]]; then
                has_diff=1
            fi
        done

        for result in "${results[@]}"; do
            local name="${result%%:*}"
            local rest="${result#*:}"
            local server="${rest%%:*}"
            local value="${rest#*:}"
            if [[ -z "$value" ]]; then
                printf "  %-12s (%s): ${C}(no record)${N}\n" "$name" "$server"
            else
                printf "  %-12s (%s): %s\n" "$name" "$server" "$value"
            fi
        done

        if (( has_diff )); then
            echo -e "  ${Y}Status: PROPAGATING${N}"
            global_ok=0
        else
            echo -e "  ${G}Status: SYNCED${N}"
        fi
        echo ""
    done

    echo -e "${B}==============================================================${N}"
    echo -e "📝 ${B}Summary:${N}"

    if (( global_ok )); then
        echo -e "✅ ${G}PROPAGATION COMPLETE${N}"
        echo "   全てのレコードが世界中のDNSサーバーで同期されています。"
    else
        echo -e "⏳ ${Y}PROPAGATION IN PROGRESS${N}"
        echo "   一部のレコードがDNSサーバー間で異なっています。"
        echo "   これは正常です。DNS変更の反映には最大48時間かかります。"
    fi
    echo ""

    echo -e "${B}💡 この結果の意味${N}"
    echo "────────────────────────────────────────────────────────"
    echo -e "  ${G}SYNCED${N}     : 全サーバーで同じ値。問題なし。"
    echo -e "  ${Y}PROPAGATING${N}: まだ伝播中。数時間後に再確認してください。"
    echo ""
    echo -e "${B}📋 次にやること${N}"
    echo "────────────────────────────────────────────────────────"
    if (( global_ok )); then
        echo "  ✓ 伝播完了！特に対応は不要です。"
        echo "  ✓ Webサイトやメールが正常に動作するか確認してください。"
    else
        echo "  1. 数時間〜24時間待ってから再度このコマンドを実行"
        echo "  2. 48時間経っても同期しない場合は、DNS設定を確認"
        echo "  3. TTLが長い場合は、キャッシュが切れるまで時間がかかります"
    fi
    echo ""
}

check_migration() {
    local domain=$1 target_hint=$2

    echo -e "${B}==============================================================${N}"
    echo -e " Full Mesh DNS Migration Check: ${C}${domain}${N}"
    echo -e "    Discovery Node: ${target_hint}"
    echo -e "${B}==============================================================${N}"

    echo -n "Discovering all target nameservers..."

    # まずネームサーバー自体が存在するか確認
    local ns_check
    ns_check=$(dig "$target_hint" A +short 2>/dev/null || true)

    if [[ -z "$ns_check" ]]; then
        echo -e " ${R}[FAILED]${N}"
        echo ""
        echo -e "${R}エラー: ネームサーバー ${target_hint} が見つかりません${N}"
        echo ""
        echo -e "${B}💡 これはどういう状況？${N}"
        echo "────────────────────────────────────────────────────────"
        echo "  指定されたネームサーバーのアドレスが存在しません。"
        echo "  タイプミス、または架空のサーバー名の可能性があります。"
        echo ""
        echo -e "${B}📋 確認してください${N}"
        echo "────────────────────────────────────────────────────────"
        echo "  1. ネームサーバー名が正しいか確認"
        echo "  2. 移行先のDNSプロバイダの管理画面で、正しいNS名を確認"
        echo ""
        echo "  例："
        echo "    - Google Cloud DNS: ns-cloud-XX.googledomains.com"
        echo "    - AWS Route53: ns-XXX.awsdns-XX.org"
        echo "    - Cloudflare: XXX.ns.cloudflare.com"
        exit 1
    fi

    local target_ns_list
    target_ns_list=$(dig "@$target_hint" "$domain" NS +short 2>/dev/null | sort || true)

    if [[ -z "$target_ns_list" ]]; then
        echo -e " ${R}[FAILED]${N}"
        echo ""
        echo -e "${R}エラー: ${target_hint} に ${domain} のゾーンが見つかりません${N}"
        echo ""
        echo -e "${B}💡 これはどういう状況？${N}"
        echo "────────────────────────────────────────────────────────"
        echo "  ネームサーバー自体は存在しますが、"
        echo "  このドメインのDNSゾーンがまだ作成されていません。"
        echo ""
        echo -e "${B}📋 このコマンドを使うタイミング${N}"
        echo "────────────────────────────────────────────────────────"
        echo ""
        echo "  【移行の流れ】"
        echo "    1. 移行先のDNSプロバイダで ${domain} のゾーンを作成"
        echo "    2. 現在のDNSレコードを移行先にコピー"
        echo -e "    3. ${B}このコマンドで確認${N} ← 今ここで使う"
        echo "    4. 問題なければレジストラでNSを切り替え"
        echo ""
        echo "  まだ移行先にゾーンを作成していない場合は、"
        echo "  先にゾーンを作成してからこのコマンドを実行してください。"
        echo ""
        echo -e "${B}📊 現在の ${domain} の状態を確認するには${N}"
        echo "────────────────────────────────────────────────────────"
        echo "  just dns-lookup ${domain}"
        echo "  just dns-propagation ${domain}"
        exit 1
    fi

    local -a ns_servers=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && ns_servers+=("$line")
    done <<< "$target_ns_list"
    local count=${#ns_servers[@]}

    echo -e " ${G}[OK]${N}"
    echo -e "   Found ${B}$count${N} authoritative servers:"
    for ns in "${ns_servers[@]}"; do echo "    - $ns"; done
    echo "----------------------------------------------------------------------------------"

    local record_types=("A" "AAAA" "CNAME" "MX" "TXT")
    local global_missing_error=0 global_diff_warn=0

    printf "%-6s | %-28s | %-16s | %s\n" "TYPE" "LIVE VALUE (Excerpt)" "STATUS" "TARGET CONSISTENCY"
    echo "----------------------------------------------------------------------------------"

    for type in "${record_types[@]}"; do
        local live_val
        live_val=$(dig "$domain" "$type" +short | sort | grep -v "^$" || true)

        local disp_live
        disp_live=$(echo "$live_val" | tr '\n' ',' | sed 's/,$//' | cut -c 1-28)
        [[ -z "$disp_live" ]] && disp_live="${C}(None)${N}"
        [[ ${#disp_live} -ge 28 ]] && disp_live="${disp_live}..."

        [[ -z "$live_val" ]] && continue

        local missing_servers="" diff_servers="" match_count=0

        for ns in "${ns_servers[@]}"; do
            local target_val
            target_val=$(dig "@$ns" "$domain" "$type" +short | sort | grep -v "^$" || true)

            if [[ -z "$target_val" ]]; then
                missing_servers+="$ns "
            elif [[ "$live_val" != "$target_val" ]]; then
                diff_servers+="$ns "
            else
                match_count=$((match_count + 1))
            fi
        done

        local status result
        if [[ -n "$missing_servers" ]]; then
            status="MISSING"
            local sample; sample=$(echo "$missing_servers" | awk '{print $1}')
            [[ $(echo "$missing_servers" | wc -w) -gt 1 ]] && sample="$sample +others"
            result="Missing on: $sample"
            global_missing_error=1
            printf "%-6s | %-38s | ${R}%-16s${N} | ${R}%s${N}\n" "$type" "$disp_live" "$status" "$result"
        elif [[ -n "$diff_servers" ]]; then
            status="DIFF"
            result="Values differ (IP change?)"
            global_diff_warn=1
            printf "%-6s | %-38s | ${Y}%-16s${N} | ${Y}%s${N}\n" "$type" "$disp_live" "$status" "$result"
        else
            status="SYNCED"
            result="Match on all $count servers"
            printf "%-6s | %-38s | ${G}%-16s${N} | ${G}%s${N}\n" "$type" "$disp_live" "$status" "$result"
        fi
    done

    echo "----------------------------------------------------------------------------------"
    echo -e "📝 ${B}Summary:${N}"

    if (( global_missing_error )); then
        echo -e "🚫 ${R}CRITICAL: レコード欠落を検出${N}"
        echo "   現在のDNSにあるレコードが、移行先に存在しません。"
    elif (( global_diff_warn )); then
        echo -e "⚠️  ${Y}WARNING: 値の相違を検出${N}"
        echo "   レコードは存在しますが、値が異なります。"
    else
        echo -e "✅ ${G}PERFECT: 移行準備完了${N}"
        echo "   全てのレコードが移行先と一致しています。"
    fi
    echo ""

    echo -e "${B}💡 ステータスの意味${N}"
    echo "────────────────────────────────────────────────────────"
    echo -e "  ${G}SYNCED${N}  : 現在のDNSと移行先が完全一致。問題なし。"
    echo -e "  ${Y}DIFF${N}    : 値が異なる。意図的な変更なら問題なし。"
    echo -e "  ${R}MISSING${N} : 移行先にレコードがない。${R}危険${N}。追加が必要。"
    echo ""

    echo -e "${B}📋 次にやること${N}"
    echo "────────────────────────────────────────────────────────"
    if (( global_missing_error )); then
        echo -e "  ${R}⚠️  まだNSレコードを切り替えないでください！${N}"
        echo ""
        echo "  1. 移行先のDNS管理画面を開く"
        echo "  2. 上記の MISSING レコードを追加する"
        echo "  3. このコマンドを再実行して確認"
        echo "  4. 全て SYNCED になったら NS を切り替え可能"
    elif (( global_diff_warn )); then
        echo "  値が異なる理由を確認してください："
        echo ""
        echo "  ● サーバー移行（IPアドレス変更）の場合 → 問題なし、想定通り"
        echo "  ● DNS管理のみ移行（IP同じ）の場合 → タイプミスの可能性あり"
        echo ""
        echo "  確認できたら、レジストラでNSレコードを切り替えてOKです。"
        echo "  切り替え後は --propagation で伝播状況を監視してください。"
    else
        echo "  全てのレコードが一致しています。移行を実行できます。"
        echo ""
        echo "  1. ドメインレジストラの管理画面を開く"
        echo "  2. NSレコードを新しいネームサーバーに変更"
        echo "  3. 変更後、以下のコマンドで伝播を監視："
        echo "     just dns-propagation ${domain}"
    fi
    echo ""
}

# --- Main ---

if ! command -v dig &> /dev/null; then
    echo -e "${R}Error: 'dig' command not found.${N}"
    echo "Install: brew install bind (macOS) or apt install dnsutils (Linux)"
    exit 1
fi

PROPAGATION_MODE=0 DOMAIN="" TARGET_NS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--propagation) PROPAGATION_MODE=1; shift ;;
        -h|--help) show_help; exit 0 ;;
        -*) echo -e "${R}Error: Unknown option: $1${N}"; show_help; exit 1 ;;
        *)
            if [[ -z "$DOMAIN" ]]; then DOMAIN="$1"
            elif [[ -z "$TARGET_NS" ]]; then TARGET_NS="${1#@}"
            else echo -e "${R}Error: Too many arguments.${N}"; show_help; exit 1
            fi
            shift ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then
    echo -e "${R}Error: Domain is required.${N}"
    show_help
    exit 1
fi

if (( PROPAGATION_MODE )); then
    check_propagation "$DOMAIN"
else
    if [[ -z "$TARGET_NS" ]]; then
        echo -e "${R}Error: Target nameserver required for migration check.${N}"
        echo "Use: $(basename "$0") <domain> <target_ns> or $(basename "$0") -p <domain>"
        exit 1
    fi
    check_migration "$DOMAIN" "$TARGET_NS"
fi
