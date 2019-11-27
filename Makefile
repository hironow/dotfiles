deploy: ## Create symlink to home directory
	@ echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc

clean: ## Remove the dot files and this repo
	@ echo "==> Remove dot files in your home directory..."
	rm -vrf ~/.zshrc

circleci: ## CircleCI local execute
	circleci config process .circleci/config.yml > .circleci/config-2.0.yml
	circleci local execute -c .circleci/config-2.0.yml --job shellcheck/check

dump: ## Dump current brew bundle
	rm Brewfile && brew bundle dump

add-gcloud: ## Install gcloud components
	@ gcloud components install `awk '{ORS=" "} {print}' gcloud`

add-yarn-global: ## Add yarn global packages
	@ yarn global add `awk '{ORS=" "} {print}' yarn-global`

help: ## Self-documented Makefile
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: deploy clean circleci dump add-gcloud add-yarn-global help