deploy: ## Create symlink to home directory
	@ echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc
	ln -s ~/dotfiles/.zshrc.antigen ~/.zshrc.antigen

clean: ## Remove the dot files and this repo
	@ echo "Remove dot files in your home directory..."
	rm -vrf ~/.zshrc
	rm -vrf ~/.zshrc.antigen

circleci: ## CircleCI local execute
	circleci config process .circleci/config.yml > .circleci/config-2.0.yml
	circleci local execute -c .circleci/config-2.0.yml --job shellcheck/check

dump: ## Dump current bundle
	rm Brewfile && brew bundle dump

help: ## Self-documented Makefile
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: deploy clean circleci dump help