#!/bin/bash
# Code Server セットアップスクリプト（タスクランナーのラッパー）

set -e

# 使用方法
usage() {
    cat << EOF
Code Server セットアップスクリプト

使用方法: $0 [OPTIONS]

Options:
    -i, --instance-id ID            対象のEC2インスタンスID (必須)
    -r, --region REGION             AWSリージョン (デフォルト: sa-east-1)
    -u, --user USERNAME             Code Serverユーザー名 (デフォルト: coder)
    -p, --password PASSWORD         Code Serverパスワード (省略時はSecrets Managerから取得)
    -s, --secret-arn ARN            Secrets Manager ARN (パスワード自動取得用)
    -d, --home-dir DIR              ホームディレクトリ (デフォルト: /work)
    --internal-port PORT            Code Server内部ポート (デフォルト: 8080)
    --nginx-port PORT               nginx外部ポート (デフォルト: 80)
    --start-from TASK_ID            指定したタスクIDから再開
    --clean-state                   状態ファイルをクリーンして最初から実行
    --dry-run                       実際には実行せず、タスクを表示のみ
    --reboot                        セットアップ完了後にインスタンスをリブート
    -h, --help                      このヘルプを表示

例:
    # 基本的な使用方法
    $0 -i i-1234567890abcdef0

    # Secrets Managerからパスワードを取得
    $0 -i i-1234567890abcdef0 -s arn:aws:secretsmanager:...

    # パスワードを直接指定
    $0 -i i-1234567890abcdef0 -p MySecurePassword123

    # 特定のタスクから再開
    $0 -i i-1234567890abcdef0 --start-from 09-install-code-server

    # ドライラン（実行内容の確認）
    $0 -i i-1234567890abcdef0 --dry-run

    # セットアップ後にリブート
    $0 -i i-1234567890abcdef0 --reboot
EOF
}

# デフォルト値
INSTANCE_ID=""
REGION="sa-east-1"
USER="coder"
PASSWORD=""
SECRET_ARN=""
HOME_DIR="/work"
INTERNAL_PORT="8080"
NGINX_PORT="80"
START_FROM=""
CLEAN_STATE=false
DRY_RUN=false
REBOOT=false

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--instance-id)
            INSTANCE_ID="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -u|--user)
            USER="$2"
            shift 2
            ;;
        -p|--password)
            PASSWORD="$2"
            shift 2
            ;;
        -s|--secret-arn)
            SECRET_ARN="$2"
            shift 2
            ;;
        -d|--home-dir)
            HOME_DIR="$2"
            shift 2
            ;;
        --internal-port)
            INTERNAL_PORT="$2"
            shift 2
            ;;
        --nginx-port)
            NGINX_PORT="$2"
            shift 2
            ;;
        --start-from)
            START_FROM="$2"
            shift 2
            ;;
        --clean-state)
            CLEAN_STATE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --reboot)
            REBOOT=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "エラー: 不明なオプション: $1"
            usage
            exit 1
            ;;
    esac
done

# 必須パラメータチェック
if [[ -z "$INSTANCE_ID" ]]; then
    echo "エラー: インスタンスIDが指定されていません (-i オプション必須)"
    usage
    exit 1
fi

echo "========================================="
echo "Code Server セットアップ"
echo "========================================="
echo "インスタンスID: $INSTANCE_ID"
echo "リージョン: $REGION"
echo "ユーザー: $USER"
echo "ホームディレクトリ: $HOME_DIR"
echo "内部ポート: $INTERNAL_PORT"
echo "外部ポート (nginx): $NGINX_PORT"
echo "========================================="

# パスワード取得（指定がない場合）
if [[ -z "$PASSWORD" ]]; then
    if [[ -n "$SECRET_ARN" ]]; then
        echo "📦 Secrets Managerからパスワードを取得中..."
        PASSWORD=$(aws secretsmanager get-secret-value \
            --secret-id "$SECRET_ARN" \
            --region "$REGION" \
            --query 'SecretString' \
            --output text)
        echo "✅ パスワード取得成功"
    else
        echo "⚠️  警告: パスワードが指定されていません。ランダムパスワードを生成します。"
        PASSWORD=$(openssl rand -base64 12)
        echo "🔑 生成されたパスワード: $PASSWORD"
    fi
fi

# スクリプトのディレクトリ取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TASK_FILE="$PROJECT_DIR/tasks/code-server-setup.json"

# タスクファイルの存在確認
if [[ ! -f "$TASK_FILE" ]]; then
    echo "❌ エラー: タスク定義ファイルが見つかりません: $TASK_FILE"
    exit 1
fi

# 変数定義（JSON形式）
VARIABLES_JSON=$(cat << EOF
{
    "USER": "$USER",
    "PASSWORD": "$PASSWORD",
    "HOME_DIR": "$HOME_DIR",
    "INTERNAL_PORT": "$INTERNAL_PORT",
    "NGINX_PORT": "$NGINX_PORT"
}
EOF
)

# タスクランナー実行
RUN_TASKS_ARGS=(
    -i "$INSTANCE_ID"
    -r "$REGION"
    -f "$TASK_FILE"
    -v "$VARIABLES_JSON"
)

if [[ -n "$START_FROM" ]]; then
    RUN_TASKS_ARGS+=(--start-from "$START_FROM")
fi

if [[ "$CLEAN_STATE" == true ]]; then
    RUN_TASKS_ARGS+=(--clean-state)
fi

if [[ "$DRY_RUN" == true ]]; then
    RUN_TASKS_ARGS+=(--dry-run)
fi

echo ""
bash "$SCRIPT_DIR/run-tasks.sh" "${RUN_TASKS_ARGS[@]}"

# 実行結果
if [[ $? -eq 0 ]]; then
    echo ""
    echo "========================================="
    echo "🎉 Code Serverセットアップ完了！"
    echo "========================================="

    # インスタンス情報取得
    PUBLIC_DNS=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'Reservations[0].Instances[0].PublicDnsName' \
        --output text 2>/dev/null || echo "N/A")

    echo ""
    echo "🌐 Code Server URL:"
    if [[ "$PUBLIC_DNS" != "N/A" && -n "$PUBLIC_DNS" ]]; then
        echo "  http://$PUBLIC_DNS:$NGINX_PORT"
    else
        echo "  http://[YOUR_INSTANCE_IP]:$NGINX_PORT"
    fi
    echo ""
    echo "🔑 パスワード:"
    echo "  $PASSWORD"
    echo ""
    echo "ℹ️  アーキテクチャ:"
    echo "  Code Server: ポート $INTERNAL_PORT"
    echo "  nginx proxy: ポート $NGINX_PORT → $INTERNAL_PORT"
    echo ""
    echo "🔌 SSM接続:"
    echo "  aws ssm start-session --target $INSTANCE_ID --region $REGION"
    echo ""
    echo "========================================="

    # リブート処理
    if [[ "$REBOOT" == true ]]; then
        echo ""
        echo "🔄 インスタンスをリブートしています..."
        echo ""
        aws ec2 reboot-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION"

        if [[ $? -eq 0 ]]; then
            echo "✅ リブート開始しました"
            echo ""
            echo "⏳ インスタンスの状態確認:"
            echo "  aws ec2 describe-instance-status --instance-ids $INSTANCE_ID --region $REGION"
            echo ""
            echo "⚠️  注意: リブート後、Code Serverが再起動するまで数分かかる場合があります"
        else
            echo "❌ リブートの開始に失敗しました"
            exit 1
        fi
    fi
else
    echo ""
    echo "❌ セットアップが失敗しました"
    echo ""
    echo "再開するには:"
    echo "  $0 -i $INSTANCE_ID -r $REGION [OPTIONS] --start-from <TASK_ID>"
    echo ""
    exit 1
fi
