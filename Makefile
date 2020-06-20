.DEFAULT_GOAL := help

.PHONY: help
help: ## Self-documented Makefile
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

cmd-exists-%:
	@hash $(*) > /dev/null 2>&1 || \
		(echo "ERROR: '$(*)' must be installed and available on your PATH."; exit 1)

guard-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: environment variable $* not set' && exit 1; fi


.PHONY: deploy
deploy: ## Create symlink to home directory
	@echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc

.PHONY: clean
clean: ## Remove the dot files and this repo
	@echo "==> Remove dot files in your home directory..."
	rm -vrf ~/.zshrc

.PHONY: circleci
circleci: cmd-exists-circleci  ## CircleCI local execute
	circleci config process .circleci/config.yml > .circleci/config-2.0.yml
	circleci local execute -c .circleci/config-2.0.yml --job shellcheck/check
	rm .circleci/config-2.0.yml

.PHONY: dump
dump: cmd-exists-brew  ## Dump current brew bundle
	rm Brewfile && brew bundle dump

# add set
.PHONY: add-brew
add-brew: cmd-exists-brew  ## Install brew bundle
	@brew bundle

.PHONY: add-gcloud
add-gcloud: cmd-exists-gcloud  ## Install gcloud components
	@gcloud components install `awk '{ORS=" "} {print}' gcloud`

.PHONY: add-yarn-global
add-yarn-global: cmd-exists-yarn  ## Install yarn global packages
	@yarn global add `awk '{ORS=" "} {print}' yarn-global`

# update set
.PHONY: update-all
update-all:  ## Install all
	@make -j update-brew update-gcloud update-yarn-global

.PHONY: update-brew
update-brew: cmd-exists-brew  ## Update brew bundle
	@brew update && brew upgrade && brew cleanup

.PHONY: update-gcloud
update-gcloud: cmd-exists-gcloud  ## Update gcloud components
	@gcloud components update

.PHONY: update-yarn-global
update-yarn-global: cmd-exists-yarn  ## Update yarn global packages
	@yarn global upgrade