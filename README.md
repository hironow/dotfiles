# dotfiles

```shell
bash -c "$(curl -L raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

> [!NOTE]  
> Mac, Linux, Windows([WSL](https://learn.microsoft.com/en-us/windows/wsl/)内Linux)へ対応

## usage

```shell
# make
make edit
make update-all
make dump

# uv on mise
mx uv sync

# make on mise
mx make

# mise env
mx dotenvx run -- mise set
# mise env with github credentials (use gh extension)
gh do -- mise set

# set env by dotenvx (encrypted)
mx dotenvx set HELLO World
# set env by mise (plain, unencrypted)
mx mise set WORLD=hello
```

## setup

```shell
# check A record for localhost -> 127.0.0.1
dig localhost.hironow.dev

# create/update cert for https
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ${config_root}/private/certificates

# check simple-server for https localhost
cd tools/simple-server
sudo mise x -- go run main.go
```

## references

- [mise](https://github.com/jdx/mise)
- [uv](https://github.com/astral-sh/uv)
- [gh do](https://github.com/k1LoW/gh-do)
- [localhost](https://blog.jxck.io/entries/2020-06-29/https-for-localhost.html)
- [dotenvx](https://dotenvx.com/)
- [browser toolbox](https://toolbox.googleapps.com/)
- [smarthome webrtc tool](https://smarthome-webrtc-validator.withgoogle.com/)
