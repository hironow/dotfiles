# dotfiles

```shell
bash -c "$(curl -L raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

> [!NOTE]  
> Mac, Linux, Windows([WSL](https://learn.microsoft.com/en-us/windows/wsl/)内Linux)へ対応

```shell
# make
make edit
make update-all
make dump

# uv on mise (use x)
x uv sync

# make on mise
x make

# mise env
mise set

# mise env with github credentials (use gh extension)
gh do -- mise set
```

## references

- [mise](https://github.com/jdx/mise)
- [uv](https://github.com/astral-sh/uv)
- [gh do](https://github.com/k1LoW/gh-do)
- [localhost](https://blog.jxck.io/entries/2020-06-29/https-for-localhost.html)
