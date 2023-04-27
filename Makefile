.DEFAULT_GOAL := help

.PHONY: help deploy clean dump add-all add-brew add-gcloud add-npm-global update-all update-brew update-gcloud update-npm-global check-brew check-gcloud check-npm-global check-npm-global

help: ## Self-documented Makefile
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

cmd-exists-%:
	@hash $(*) > /dev/null 2>&1 || \
		(echo "ERROR: '$(*)' must be installed and available on your PATH."; exit 1)

guard-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: environment variable $* not set' && exit 1; fi


deploy: ## Create symlink to home directory
	@echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc

clean: ## Remove the dotfiles
	@echo "==> Remove dotfiles in your home directory..."
	rm -vrf ~/.zshrc

dump: cmd-exists-brew  ## Dump current brew bundle
	rm Brewfile && brew bundle dump

# add set
add-all:  ## Install all
	@make -j 3 add-brew add-gcloud add-npm-global

add-brew: cmd-exists-brew  ## Install brew bundle
	brew bundle

add-gcloud: cmd-exists-gcloud  ## Install gcloud components
	gcloud components install `awk '{ORS=" "} {print}' gcloud`

add-npm-global: cmd-exists-npm  ## Install npm global packages
	npm install --global `awk '{ORS=" "} {print}' npm-global`

# update set
update-all:  ## Update all
	@make -j 3 update-brew update-gcloud update-npm-global

update-brew: cmd-exists-brew  ## Update brew bundle
	brew update && brew upgrade && brew cleanup

update-gcloud: cmd-exists-gcloud  ## Update gcloud components
	gcloud components update --quiet

update-npm-global: cmd-exists-npm  ## Update npm global packages
	npm update --global

# check set
check-brew: cmd-exists-brew  ## Check brew bundle
	brew list

check-gcloud: cmd-exists-gcloud  ## Check gcloud components
	gcloud components list

check-npm-global: cmd-exists-npm  ## Check npm global packages
	npm ls --global --depth 0
