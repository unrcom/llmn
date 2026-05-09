# llamune セットアップ手順

このドキュメントでは、llamune を新しい macOS 環境にゼロからセットアップする手順を説明します。

## 前提条件

- macOS（Apple Silicon）
- インターネット接続
- GitHub アカウント（リポジトリへのアクセス権限）

## 1. 前提ソフトウェアのインストール

### Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

インストール後、PATH を通します。

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Git

```bash
brew install git
```

Git のユーザー情報を設定します。

```bash
git config --global user.name "your-name"
git config --global user.email "your-email@example.com"
```

### Docker Desktop

```bash
brew install --cask docker
```

インストール後、Docker Desktop を起動し、初期設定を完了させてください。

```bash
open /Applications/Docker.app
```

### Node.js（nvm 経由）

Node.js は nvm（Node Version Manager）経由で LTS 版をインストールします。

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.zshrc
nvm install --lts
```

### Python

```bash
brew install python
```

## 2. リポジトリのクローン

```bash
git clone https://github.com/unrcom/llamune.git
cd llamune
```

## 3. データベースの起動

### 環境変数の設定

ルートディレクトリに `.env` ファイルを作成します。

```bash
cp .env.example .env
```

`.env` を編集し、データベースの認証情報を設定してください。

```
POSTGRES_USER=llmn
POSTGRES_PASSWORD=llmn
POSTGRES_DB=llmndb
```

> ⚠️ 本番環境では `POSTGRES_PASSWORD` を必ず安全な値に変更してください。

### Docker Compose の起動

Docker Desktop が起動していることを確認してから実行してください。

```bash
docker compose up -d
```

PostgreSQL がポート 5434 で起動します。

起動確認：

```bash
docker compose ps
```

`llmn_db` コンテナが `running` 状態であることを確認してください。

## 4. データベースマイグレーション

```bash
cd llmn_db
npm install
```

`.env` ファイルを作成します。

```bash
cp .env.example .env
```

`.env` を編集し、接続情報を設定してください（ポートは 5434）。

```
DATABASE_URL=postgres://llmn:llmn@localhost:5434/llmndb
```

マイグレーションを実行します。

```bash
npm run migrate:up
```

```bash
cd ..
```

## 5. バックエンドのセットアップ

```bash
cd back
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` ファイルを作成します。

```bash
cp .env.example .env
```

`.env` を編集してください。`DATABASE_URL` のスキーマは `postgresql://` を使用し、`JWT_SECRET` を安全な値に変更してください。

```
DATABASE_URL=postgresql://llmn:llmn@localhost:5434/llmndb
JWT_SECRET=your-secret-key-here
JWT_EXPIRE_MINUTES=60
```

> ⚠️ バックエンド（SQLAlchemy）では `postgresql://` を使用してください。`postgres://` ではエラーになります。

### 初期ユーザーの作成

```bash
python create_user.py <ユーザー名> <パスワード> --admin
```

### バックエンドの起動

```bash
uvicorn app.main:app --reload --port 8000
```

## 6. フロントエンドのセットアップ

別のターミナルを開いて実行してください。

```bash
cd llamune/web
npm install
npm run dev
```

フロントエンドがポート 5174 で起動します。

## 7. 動作確認

ブラウザで http://localhost:5174 にアクセスし、作成したユーザーでログインできることを確認してください。

## 停止方法

フロントエンド・バックエンドはそれぞれのターミナルで `Ctrl+C` で停止します。

データベースの停止：

```bash
docker compose down
```

データベースのデータは Docker ボリューム `llmn_db_data` に保持されるため、再起動してもデータは失われません。
