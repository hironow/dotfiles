# https://just.systems

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default: help

help:
    @just --list --unsorted


# ------------------------------
# Project Management
# ------------------------------

install:
    # Install tools via mise (versions are managed in mise.toml)
    mise install

deploy:
    @echo "==> Start to deploy dotfiles to home directory."
    ln -sf ~/dotfiles/.zshrc ~/.zshrc

clean:
    @echo "==> Remove dotfiles in your home directory..."
    rm -vrf ~/.zshrc

dump:
    # Dump current brew bundle
    rm -f ./dump/Brewfile && (cd ./dump && brew bundle dump)

freeze:
    # Freeze current python packages using uv
    uv pip freeze | uv pip compile - -o requirements.txt


# ------------------------------
# Add sets
# ------------------------------

add-all:
    just add-gcloud
    just add-brew
    just add-pnpm-g

add-brew:
    # Install brew bundle
    (cd ./dump && brew bundle)

add-gcloud:
    # Install gcloud components
    sudo gcloud components install $(awk '{ORS=" "} {print}' ./dump/gcloud)

add-pnpm-g:
    # Install pnpm global packages
    pnpm add --global $(awk '{ORS=" "} {print}' ./dump/npm-global)


# ------------------------------
# Update sets
# ------------------------------

update-all:
    just update-gcloud
    just update-brew
    just update-pnpm-g
    @echo "◆ mise..."
    mise up
    mise plugins up
    @echo "◆ gh..."
    gh extension upgrade --all
    @echo "◆ tldr..."
    tldr --update
    @echo "◆ gitignore..."
    git ignore --update
    @echo "◆ vscode extensions..."
    code --update-extensions

update-brew:
    @echo "◆ homebrew..."
    brew update && brew upgrade && brew cleanup

update-gcloud:
    @echo "◆ gcloud..."
    sudo gcloud components update --quiet

update-pnpm-g:
    @echo "◆ pnpm..."
    pnpm update --global


# ------------------------------
# Check sets
# ------------------------------

check-path:
    # Check PATH
    @echo $${PATH//:/\\n}

check-myip:
    # Check my ip address
    @ifconfig | sed -En "s/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p"

check-dockerport:
    # Check docker port
    @docker ps -q | xargs docker inspect | jq '.[] | {name: .Name, ports: .NetworkSettings.Ports}'

check-brew:
    brew list

check-gcloud:
    gcloud components list

check-npm-g:
    npm ls --global --depth 0

check-pnpm-g:
    pnpm list -g --depth=0

check-rust:
    rustc --print cfg


# ------------------------------
# Connect sets
# ------------------------------

connect-gcloud-sql:
    # Requires env: GCLOUD_SQL_INSTANCE, LOCAL_SQL_PORT
    [[ -n "${GCLOUD_SQL_INSTANCE:-}" ]] || { echo 'ERROR: environment variable GCLOUD_SQL_INSTANCE not set'; exit 1; }
    [[ -n "${LOCAL_SQL_PORT:-}" ]] || { echo 'ERROR: environment variable LOCAL_SQL_PORT not set'; exit 1; }
    cloud_sql_proxy -instances=${GCLOUD_SQL_INSTANCE}=tcp:${LOCAL_SQL_PORT}

connect-azurite:
    azurite --silent --location .azurite --debug .azurite/debug.log


# ------------------------------
# Cloud sets
# ------------------------------

gcloud-list:
    gcloud config configurations list

azure-list:
    az account list --output table

aws-list:
    aws configure list-profiles

elt-list:
    dataform listtables bigquery


# ------------------------------
# Version checks
# ------------------------------

check-version-nvcc expected:
    # Usage: just check-version-nvcc <EXPECTED_NVCC_VERSION>
    version=$(nvcc --version | grep "release" | awk '{print $$6}' | cut -d ',' -f 1)
    if [ "${version}" != "{{expected}}" ]; then
        echo "ERROR: Expected NVCC version {{expected}}, but found ${version}"
        exit 1
    fi

check-version-torch expected:
    # Usage: just check-version-torch <EXPECTED_TORCH_VERSION>
    version=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || true)
    if [ -z "${version}" ]; then
        echo "ERROR: PyTorch is not installed"
        exit 1
    elif [ "${version}" != "{{expected}}" ]; then
        echo "ERROR: Expected PyTorch version {{expected}}, but found ${version}"
        exit 1
    fi


# ------------------------------
# TLS checks
# ------------------------------

check-localhost-tls:
    # Serve TLS on localhost using the Go simple-server
    mise x -- sudo go run tools/simple-server/main.go
