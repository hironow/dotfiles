# ASCII Diagrams in Responses

Read this when you are about to include an ASCII diagram, box-art, or flow
sketch in a response. Claude-specific; the root rule + pointer is in CLAUDE.md.

- Use **single-byte ASCII only** inside the diagram — no Japanese/Chinese/
  Korean/emoji. Multi-byte characters break monospace alignment.
- Always add a legend directly below the diagram, with Japanese glosses unless
  told otherwise (`English term: 日本語`).

Worked example:

```
+-------------------+
|  Request Handler  |
+-------------------+
         |
         v
+-------------------+
|     Validator     |
+-------------------+

Legend / 凡例:
- Request Handler: リクエストハンドラー
- Validator: バリデーター
```
