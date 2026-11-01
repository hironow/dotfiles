# Elasticsearch CLI

Interactive shell for the Elasticsearch REST API. Start Elasticsearch
(`just emu-up-group search`), then run from `emulator/`:

```bash
docker compose --profile cli run --rm elasticsearch-cli
```

Type a request as `METHOD /path [json body];`. The request runs when a line
ends with `;`, so a body can span several lines. Each response is
pretty-printed with its run time.

```text
PUT /products {"settings": {"number_of_shards": 1, "number_of_replicas": 0}};
POST /products/_doc {"name": "Laptop", "price": 999.99};
GET /products/_search {"query": {"match": {"name": "laptop"}}};
DELETE /products;
```

After `PUT /<index>`, the CLI waits up to 60 seconds for the index shards to
be ready.

The CLI joins lines with spaces, so newline-delimited APIs such as `_bulk` do
not work. Use `curl` for those.

Shell commands (backslash only):

- `\h`, `\help`: help and examples
- `\l`, `\indices`: list indices as a table
- `\i`, `\info`: cluster info
- `\health`: cluster health
- `\c`, `\clear`: clear the screen
- `\q`, `\quit`, `\exit`: quit

Environment:

- `ELASTICSEARCH_HOST`: default `localhost` (`elasticsearch` in Compose)
- `ELASTICSEARCH_PORT`: default `9200`
- `ES_CLI_VERBOSE`: `1` or `true` logs each index-readiness check
