.DEFAULT_GOAL := help

.PHONY: help
help: ## Self-documented Makefile
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: deploy
deploy: ## Create symlink to home directory
	@ echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc

.PHONY: clean
clean: ## Remove the dot files and this repo
	@ echo "==> Remove dot files in your home directory..."
	rm -vrf ~/.zshrc

.PHONY: circleci
circleci: ## CircleCI local execute
	circleci config process .circleci/config.yml > .circleci/config-2.0.yml
	circleci local execute -c .circleci/config-2.0.yml --job shellcheck/check

.PHONY: dump
dump: ## Dump current brew bundle
	rm Brewfile && brew bundle dump

.PHONY: add-gcloud
add-gcloud: ## Install gcloud components
	@ gcloud components install `awk '{ORS=" "} {print}' gcloud`

.PHONY: add-yarn-global
add-yarn-global: ## Add yarn global packages
	@ yarn global add `awk '{ORS=" "} {print}' yarn-global`