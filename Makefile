SHELL := $(shell which bash) # Use bash syntax to be consistent

OS_NAME := $(shell uname -s | tr '[:upper:]' '[:lower:]')
ARCH_NAME_RAW := $(shell uname -m)

GIT_ROOT := $(shell git rev-parse --show-toplevel)
COMMIT := $(shell git describe --tags --always)

LOCAL_BIN := $(CURDIR)/bin
PATH := $(LOCAL_BIN):$(PATH)


# 'make' command will trigger the help target
.DEFAULT_GOAL := help
help: ## Display this help screen
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


# utils
cmd-exists-%:
	@hash $(*) > /dev/null 2>&1 || (echo "ERROR: '$(*)' must be installed and available on your PATH."; exit 1)

guard-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: environment variable $* not set' && exit 1; fi


# this repository specific
install: cmd-exists-mise  ## Install this repository requirements
	mise install
.PHONY: install

edit: cmd-exists-code ## Open this repository with VSCode
	@code dotfiles.code-workspace
.PHONY: edit

deploy: ## Create symlink to home directory
	@echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc
.PHONY: deploy

clean: ## Remove the dotfiles
	@echo "==> Remove dotfiles in your home directory..."
	rm -vrf ~/.zshrc
.PHONY: clean

dump: cmd-exists-brew  ## Dump current brew bundle
	rm ./dump/Brewfile && cd ./dump && brew bundle dump && cd --
.PHONY: dump

freeze: cmd-exists-uv  ## Freeze current python packages
	uv pip freeze | uv pip compile - -o requirements.txt
.PHONY: freeze


# add set
add-all:  ## Install all
	make add-brew
	make add-bun-g
	make add-gcloud
.PHONY: add-all

add-brew: cmd-exists-brew  ## Install brew bundle
	cd ./dump && brew bundle && cd --
.PHONY: add-brew

add-gcloud: cmd-exists-gcloud  ## Install gcloud components
	sudo gcloud components install `awk '{ORS=" "} {print}' ./dump/gcloud`
.PHONY: add-gcloud

add-bun-g: cmd-exists-bun  ## Install bun global packages
	bun install --global `awk '{ORS=" "} {print}' ./dump/npm-global`
.PHONY: add-bun-g


# update set
update-all: cmd-exists-mise cmd-exists-gh  ## Update all
	make update-brew
	make update-bun-g
	make update-gcloud
	mise upgrade
	mise x -- uv sync
	gh extension upgrade --all
.PHONY: update-all

update-brew: cmd-exists-brew  ## Update brew bundle
	brew update && brew upgrade && brew cleanup
.PHONY: update-brew

update-gcloud: cmd-exists-gcloud  ## Update gcloud components
	sudo gcloud components update --quiet
.PHONY: update-gcloud

update-bun-g: cmd-exists-bun  ## Update bun global packages
	bun update --global
.PHONY: update-bun-g


# check set
check-path:  ## Check PATH
	@echo $${PATH//:/\\n}
.PHONY: check-path

check-myip: ## Check my ip address
	@ifconfig | sed -En "s/127.0.0.1//;s/.*inet (addr:)?(([0-9]*\.){3}[0-9]*).*/\2/p"
.PHONY: check-myip

check-dockerport: cmd-exists-docker cmd-exists-jq ## Check docker port
	@docker ps -q | xargs docker inspect | jq '.[] | {name: .Name, ports: .NetworkSettings.Ports}'

check-brew: cmd-exists-brew  ## Check brew bundle
	brew list
.PHONY: check-brew

check-gcloud: cmd-exists-gcloud  ## Check gcloud components
	gcloud components list
.PHONY: check-gcloud

check-npm-g: cmd-exists-npm  ## Check npm global packages
	npm ls --global --depth 0
.PHONY: check-npm-g

check-bun-g: cmd-exists-bun  ## Check bun global packages
	bun pm ls --global
.PHONY: check-bun-g

check-rust: cmd-exists-rustc  ## Check rust config
	rustc --print cfg
.PHONY: check-rust


# database set
connect-gcp-sql: cmd-exists-cloud_sql_proxy guard-GCP_SQL_INSTANCE guard-LOCAL_SQL_PORT  ## Connect to CloudSQL(GCP)
	cloud_sql_proxy -instances=${GCP_SQL_INSTANCE}=tcp:${LOCAL_SQL_PORT}
.PHONY: connect-gcp-sql

connect-firebase: cmd-exists-firebase  ## Connect to Firebase(GCP)
	firebase emulators:start --project 'local'
.PHONY: connect-firebase

connect-azurite: cmd-exists-azurite  ## Connect to azurite(Azure)
	azurite --silent --location .azurite --debug .azurite/debug.log
.PHONY: connect-azurite

# gcp set
gcp-list: cmd-exists-gcloud  ## List GCP
	gcloud config configurations list
.PHONY: gcp-list

# azure set
azure-list: cmd-exists-az  ## List Azure
	az account list --output table
.PHONY: azure-list

# aws set 
aws-list: cmd-exists-aws  ## List AWS
	aws configure list
.PHONY: aws-list

# ELT set
elt-list: cmd-exists-dataform  ## List ELT as Dataform(GCP)
	dataform listtables bigquery
.PHONY: elt-list

# ETL set
# TODO: Dataflow(GCP)


# version check
check-version-nvcc: cmd-exists-nvcc guard-EXPECTED_NVCC_VERSION  ## Check NVCC version
	@version=$$(nvcc --version | grep "release" | awk '{print $$6}' | cut -d ',' -f 1) ; \
	if [ "$$version" != "$(EXPECTED_NVCC_VERSION)" ]; then \
		echo "ERROR: Expected NVCC version $(EXPECTED_NVCC_VERSION), but found $$version"; \
		exit 1; \
	fi
.PHONY: check-version-nvcc

check-version-torch: cmd-exists-python guard-EXPECTED_TORCH_VERSION  ## Check PyTorch version
	@version=$$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null) ; \
	if [ -z "$$version" ]; then \
		echo "ERROR: PyTorch is not installed"; \
		exit 1; \
	elif [ "$$version" != "$(EXPECTED_TORCH_VERSION)" ]; then \
		echo "ERROR: Expected PyTorch version $(EXPECTED_TORCH_VERSION), but found $$version"; \
		exit 1; \
	fi
.PHONY: check-version-torch


# tls check
check-localhost-tls: cmd-exists-mise cmd-exists-go  ## Check localhost serve TLS
	mise x -- sudo go run scripts/simple-server/main.go
.PHONY: check-localhost-tls
