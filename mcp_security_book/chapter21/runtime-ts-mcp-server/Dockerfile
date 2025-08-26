# Stage 1: Build the application
FROM node:22-alpine AS builder

WORKDIR /app

# パッケージのインストール
COPY src/package.json src/package-lock.json ./
RUN npm install

# TypeScriptのインストール
RUN npm install typescript -g

# ソースコードのコピーとビルド
COPY ./src .
RUN npm run build

# ビルド結果の確認（デバッグ用）
RUN echo "=== ビルド結果の確認 ==="
RUN ls -la
RUN find . -name "*.js" | sort
RUN echo "======================="

# Stage 2: Create the production image
FROM node:22-alpine

WORKDIR /app

# 必要なファイルのコピー
COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/*.js ./

# ログディレクトリの作成
RUN mkdir -p /app/logs

# 環境変数の設定
ENV NODE_ENV=production
ENV LOG_LEVEL=debug
ENV MCP_STATELESS=true

# ポート公開
EXPOSE 8000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget -q -O - http://localhost:8000/health || exit 1

# 起動コマンド
CMD ["node", "add.js"]
