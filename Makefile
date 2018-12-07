deploy: ## Create symlink to home directory
	@ echo "==> Start to deploy dotfiles to home directory."
	ln -s ~/dotfiles/.zshrc ~/.zshrc
	ln -s ~/dotfiles/.zshrc.antigen ~/.zshrc.antigen

clean: ## Remove the dot files and this repo
	@ echo "Remove dot files in your home directory..."
	rm -vrf ~/.zshrc
	rm -vrf ~/.zshrc.antigen

help: ## Self-documented Makefile
	@ grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: deploy clean help