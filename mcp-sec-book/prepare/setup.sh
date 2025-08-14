#!/bin/bash

# Ubuntu で mise を使用して Node.js v22、Python 3.10、uv をインストールし、動作確認を行うスクリプト

set -e  # エラーが発生した場合にスクリプトを終了

echo "========================================="
echo "mise 開発環境セットアップスクリプト開始"
echo "========================================="

# 色付きメッセージ用の関数
print_success() {
    echo -e "\033[32m✓ $1\033[0m"
}

print_info() {
    echo -e "\033[34mℹ $1\033[0m"
}

print_error() {
    echo -e "\033[31m✗ $1\033[0m"
}

print_warning() {
    echo -e "\033[33m⚠ $1\033[0m"
}

# APTロック待機関数
wait_for_apt_lock() {
    print_info "APTロックの解除を待機中..."
    while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || sudo fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
        sleep 1
    done
    print_success "APTロックが解除されました"
}

# コマンドリトライ関数
retry_command() {
    local cmd="$1"
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        print_info "コマンド実行中 (試行 $attempt/$max_attempts): $cmd"
        if eval "$cmd"; then
            print_success "コマンドが正常に実行されました"
            return 0
        else
            print_warning "コマンドが失敗しました (試行 $attempt/$max_attempts)"
            if [ $attempt -eq $max_attempts ]; then
                print_error "コマンドが最大試行回数後も失敗しました: $cmd"
                return 1
            fi
            sleep 2
            attempt=$((attempt + 1))
        fi
    done
}

# 必要なパッケージの確認とインストール
print_info "必要なパッケージの確認とインストール中..."
wait_for_apt_lock
retry_command "sudo apt update -y"
retry_command "sudo apt install -y gpg sudo wget curl"
print_success "必要なパッケージのインストールが完了しました"

# mise のインストール
print_success "miseのインストールを開始します..."

# GPGキーの追加
print_info "miseのGPGキーを追加中..."
retry_command "wget -qO - https://mise.jdx.dev/gpg-key.pub | gpg --yes --dearmor -o /tmp/mise-archive-keyring.gpg"
sudo mv /tmp/mise-archive-keyring.gpg /etc/apt/keyrings/mise-archive-keyring.gpg
print_success "GPGキーの追加が完了しました"

# リポジトリの追加
print_info "miseのリポジトリを追加中..."
echo "deb [signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg arch=amd64] https://mise.jdx.dev/deb stable main" | sudo tee /etc/apt/sources.list.d/mise.list
print_success "リポジトリの追加が完了しました"

# mise のインストール
print_info "miseをインストール中..."
wait_for_apt_lock
retry_command "sudo apt update"
wait_for_apt_lock
retry_command "sudo apt install -y mise"
print_success "miseのインストールが完了しました"

# .bashrc に mise の設定を追加
print_info "mise の設定を .bashrc に追加中..."
if ! grep -q "mise activate" ~/.bashrc; then
    echo 'eval "$(/usr/bin/mise activate bash)"' >> ~/.bashrc
    print_success "mise の設定を .bashrc に追加しました"
else
    print_success "mise の設定は既に .bashrc に存在します"
fi

# mise の設定ディレクトリとファイルの作成
print_info "mise の設定を構成中..."
mkdir -p ~/.config/mise
cat > ~/.config/mise/config.toml << 'EOF'
[tools]
uv = "0.6.16"
python = "3.10"
node = "22"

[settings]
python.uv_venv_auto = true
EOF
print_success "mise の設定ファイルを作成しました"

# mise の環境を読み込み
print_info "mise の環境を読み込み中..."
export PATH="$HOME/.local/share/mise/shims:$PATH"
eval "$(/usr/bin/mise activate bash)"

# mise でツールをインストール
print_success "miseでツールをインストール中..."
retry_command "bash -l -c '/usr/bin/mise install'"

# グローバル設定の適用
print_info "グローバル設定を適用中..."
retry_command "bash -l -c '/usr/bin/mise use -g node@22 python@3.10 uv@0.6.16'"
print_success "グローバル設定の適用が完了しました"

# シンボリックリンクの作成
print_info "シンボリックリンクを作成中..."
mkdir -p ~/.local/bin
ln -sf ~/.local/share/mise/shims/uv ~/.local/bin/uv 2>/dev/null || true
ln -sf ~/.local/share/mise/shims/python ~/.local/bin/python 2>/dev/null || true
ln -sf ~/.local/share/mise/shims/node ~/.local/bin/node 2>/dev/null || true
ln -sf ~/.local/share/mise/shims/npm ~/.local/bin/npm 2>/dev/null || true
print_success "シンボリックリンクの作成が完了しました"

# インストール確認
print_info "インストールされたツールを確認中..."
bash -l -c "/usr/bin/mise ls"

# PATH の確認
print_info "mise の PATH 設定を確認中..."
bash -l -c "echo \$PATH"

# 基本的な動作確認
print_info "基本的な動作確認を実行中..."

# 1. mise のバージョン確認
print_info "mise のバージョンを確認中..."
MISE_VERSION=$(bash -l -c "/usr/bin/mise --version" 2>/dev/null || echo "確認できませんでした")
print_success "mise バージョン: $MISE_VERSION"

# 2. Node.js の動作確認
print_info "Node.js の動作確認中..."
NODE_VERSION=$(bash -l -c "node --version" 2>/dev/null || echo "確認できませんでした")
NPM_VERSION=$(bash -l -c "npm --version" 2>/dev/null || echo "確認できませんでした")
print_success "Node.js バージョン: $NODE_VERSION"
print_success "npm バージョン: $NPM_VERSION"

# Node.js の基本動作テスト
echo "console.log('Hello, Node.js!');" > /tmp/test_node.js
NODE_OUTPUT=$(bash -l -c "node /tmp/test_node.js" 2>/dev/null || echo "")
if [ "$NODE_OUTPUT" = "Hello, Node.js!" ]; then
    print_success "Node.js の基本動作確認: OK"
else
    print_warning "Node.js の基本動作確認: 警告 (出力: $NODE_OUTPUT)"
fi
rm -f /tmp/test_node.js

# 3. Python の動作確認
print_info "Python の動作確認中..."
PYTHON_VERSION=$(bash -l -c "python --version" 2>/dev/null || echo "確認できませんでした")
print_success "Python バージョン: $PYTHON_VERSION"

# Python の基本動作テスト
echo "print('Hello, Python!')" > /tmp/test_python.py
PYTHON_OUTPUT=$(bash -l -c "python /tmp/test_python.py" 2>/dev/null || echo "")
if [ "$PYTHON_OUTPUT" = "Hello, Python!" ]; then
    print_success "Python の基本動作確認: OK"
else
    print_warning "Python の基本動作確認: 警告 (出力: $PYTHON_OUTPUT)"
fi
rm -f /tmp/test_python.py

# 4. uv の動作確認
print_info "uv の動作確認中..."
UV_VERSION=$(bash -l -c "uv --version" 2>/dev/null || echo "確認できませんでした")
print_success "uv バージョン: $UV_VERSION"

# 5. npm パッケージインストールテスト
print_info "npm パッケージインストールテスト中..."
mkdir -p /tmp/npm_test
cd /tmp/npm_test
bash -l -c "npm init -y" > /dev/null 2>&1
bash -l -c "npm install lodash" > /dev/null 2>&1

if [ -d "node_modules/lodash" ]; then
    print_success "npm パッケージインストールテスト: OK"
else
    print_warning "npm パッケージインストールテスト: 警告"
fi

# テスト用ディレクトリの削除
cd ~
rm -rf /tmp/npm_test

# シェル設定ファイルの最終確認
print_info "シェル設定ファイルの最終確認中..."
if grep -q "mise activate" ~/.bashrc; then
    print_success "mise の設定が .bashrc に正しく追加されています"
else
    print_error "mise の設定が .bashrc に見つかりません"
fi

# インストール完了メッセージ
echo ""
echo "========================================="
echo "✓ インストールが正常に完了しました！"
echo "========================================="
echo ""
echo "インストール結果:"
echo "  mise: $MISE_VERSION"
echo "  Node.js: $NODE_VERSION"
echo "  npm: $NPM_VERSION"
echo "  Python: $PYTHON_VERSION"
echo "  uv: $UV_VERSION"
echo ""
echo "使用方法:"
echo "  新しいターミナルを開くか、以下のコマンドを実行してください:"
echo "  source ~/.bashrc"
echo ""
echo "  その後、以下のコマンドで確認できます:"
echo "  mise --version"
echo "  node --version"
echo "  npm --version"
echo "  python --version"
echo "  uv --version"
echo ""
echo "mise の基本コマンド:"
echo "  mise ls                    # インストール済みツール一覧"
echo "  mise ls-remote <tool>      # インストール可能バージョン一覧"
echo "  mise install <tool>@<ver>  # 指定バージョンをインストール"
echo "  mise use <tool>@<ver>      # 指定バージョンに切り替え"
echo "  mise use -g <tool>@<ver>   # グローバルバージョンを設定"
echo ""
print_success "セットアップが完了しました！"
