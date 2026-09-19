# deepl-translator

txt / docx / pdf からテキストを抽出し、意味の切れ目でチャンク分割して DeepL API で **英語・ドイツ語 → 日本語** に翻訳します。

## セットアップ
```sh
uv sync --extra web
cp .env.example .env   # DEEPL_AUTH_KEY を記入（環境変数で直接指定してもよい）
```
Free キー（末尾 `:fx`）は `api-free.deepl.com`、それ以外は `api.deepl.com` を自動選択。

## CLI
```sh
uv run deepl-translate input.pdf -s EN -o out_ja.txt
uv run deepl-translate input.docx -s DE --bilingual -o out_ja.txt
uv run deepl-translate input.txt --dry-run          # API を呼ばず分割結果だけ確認
```

## 貼り付け整形（Shaper 相当）
PDF からコピーした文章の不要な改行・行末ハイフネーションを除去（大文字始まりの独語複合語 `Max-\nPlanck` はハイフンを残す）。
```sh
pbpaste | uv run deepl-shape | pbcopy        # 整形してクリップボードへ
pbpaste | uv run deepl-shape --url           # DeepL Web 翻訳の URL を出力
pbpaste | uv run deepl-translate - -s EN     # 整形して API で翻訳
```
Web GUI では「貼り付け整形」タブ（コピー / DeepL Web で開く / API 翻訳）。

## Web GUI
```sh
uv run streamlit run app.py
```

## 分割の仕組み
1. **チャンク（既定 4000 字以下）**: 段落 > 文 > 節（`; : ,`）> 単語 の優先順で切る。
   次の段落が入り切らなければ 4000 字未満でもそこで閉じ、段落を途中で切らない。
   文分割は英独の略語（`Dr.` `e.g.` `z.B.` `usw.`）や独語の序数（`3. Mai`）を考慮。
2. **リクエスト**: チャンクを `text[]` として、JSON ボディ ≦ 120 KiB（128 KiB 上限に余裕）かつ 50 件以下にまとめて送信。
   429 / 5xx は指数バックオフで再試行。
3. **context 自動付与（既定 ON）**: 直前チャンク末尾の数文（最大 1000 字、文の途中から始めない）を DeepL の `context` に付けて境界の文脈切れを防ぐ。
   context はリクエスト単位のため ON 時は 1 チャンク 1 リクエスト。context は課金対象外。
   `--no-auto-context` で OFF にすると複数チャンクをまとめて送信。

## テスト
```sh
uv run pytest
```
