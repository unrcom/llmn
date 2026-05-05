# llmn

⚠️ 現在開発中です。

閉域LLMを使ったRAGとファインチューニングのプラットフォームです。

## システム構成

| 項目 | 内容 |
|------|------|
| バックエンド | FastAPI (port 8000) |
| フロントエンド | React/Vite (port 5174) |
| DB | PostgreSQL (Docker, port 5434) `llmndb` スキーマ `llmn` |
| マイグレーション | node-pg-migrate (`llmn_db/`) |
| LLM | MLX |
| VectorDB | ChromaDB |
| Embedding | BAAI/bge-m3 |

## 実装済み機能

- 認証（JWT）
- プロジェクト管理
- モデル管理（HuggingFace検索・ローカルモデル・編集）
- FTデータ管理（ベース・パターン・train/valid split・JSONL出力）
- 訓練ジョブ（バックグラウンドFT実行・ポーリング・完了後モデル自動登録）
- チャット画面（FTモデル検証）

## 起動方法

```bash
# バックエンド
cd ~/dev/llmn/back
uvicorn app.main:app --reload --port 8000

# フロントエンド（別ターミナル）
cd ~/dev/llmn/web
npm run dev
```

## 停止方法

各ターミナルで `Ctrl+C`

## 再起動方法

停止後、上記の起動方法を再実行してください。

## チャット画面でのFTモデル検証

FTモデルはシステムプロンプトによって動作が大きく変わります。
学習時と同じシステムプロンプトを設定してから質問してください。

## ユーザー管理

ユーザーはコマンドラインで作成します。

```bash
cd ~/dev/llmn/back

# 一般ユーザー作成
python create_user.py <username> <password>

# 管理者ユーザー作成
python create_user.py <username> <password> --admin
```

管理者のみプロジェクト・モデル・FTデータ・訓練ジョブの管理が可能です。
