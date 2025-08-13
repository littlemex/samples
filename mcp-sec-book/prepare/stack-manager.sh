#!/bin/bash

# VS Code Server Stack Manager
# CloudFormation + EC2 + VS Code Server の操作スクリプト

set -e

# デフォルト設定
DEFAULT_REGION="us-east-1"
DEFAULT_INSTANCE_TYPE="c7i.4xlarge"
TEMPLATE_FILE="ec2-cf-vscode.yml"

# 色付きメッセージ
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_vscode() {
    echo -e "${CYAN}[VSCODE]${NC} $1"
}

# ヘルプ表示
show_help() {
    cat << EOF
🚀 VS Code Server Stack Manager

使用方法:
    $0 <command> [options]

コマンド:
    create      - VS Code Serverスタックを作成
    status      - スタック状態を確認
    monitor     - スタック作成/削除の進捗を監視
    outputs     - スタック出力値を表示
    connect     - EC2インスタンスにSSM接続
    open        - VS Code ServerをブラウザでオープンWeb
    logs        - CloudFormationイベントログを表示
    delete      - スタックを削除
    list        - 全スタック一覧
    validate    - テンプレート検証

オプション:
    -n, --name NAME         スタック名 (デフォルト: vscode-server-USERNAME)
    -r, --region REGION     AWSリージョン (デフォルト: $DEFAULT_REGION)
    -t, --type TYPE         インスタンスタイプ (デフォルト: $DEFAULT_INSTANCE_TYPE)
    -u, --user USER         VS Code Serverユーザー名 (デフォルト: coder)
    -h, --help              このヘルプを表示

インスタンスタイプ:
    • c7i.large, c7i.xlarge, c7i.2xlarge, c7i.4xlarge
    • m5.large, m5.xlarge, m5.2xlarge, m5.4xlarge
    • t3.medium, t3.large, t3.xlarge

使用例:
    # 基本的な作成
    $0 create

    # カスタム設定で作成
    $0 create -n my-vscode -t c7i.2xlarge -u developer

    # 進捗監視
    $0 monitor -n my-vscode

    # EC2に接続
    $0 connect -n my-vscode

    # ブラウザでオープン
    $0 open -n my-vscode

    # スタック削除
    $0 delete -n my-vscode

機能:
    🖥️  EC2インスタンス上でVS Code Serverが動作
    🌐 CloudFront経由でアクセス可能
    🔐 SSM Session Managerで安全に接続
    🐳 Docker、Git、AWS CLI、uvが事前インストール済み
EOF
}

# パラメータ解析
parse_args() {
    COMMAND=""
    STACK_NAME=""
    REGION="$DEFAULT_REGION"
    INSTANCE_TYPE="$DEFAULT_INSTANCE_TYPE"
    VSCODE_USER="coder"
    USER_NAME=$(whoami)

    while [[ $# -gt 0 ]]; do
        case $1 in
            create|status|monitor|outputs|connect|open|logs|delete|list|validate)
                COMMAND="$1"
                shift
                ;;
            -n|--name)
                STACK_NAME="$2"
                shift 2
                ;;
            -r|--region)
                REGION="$2"
                shift 2
                ;;
            -t|--type)
                INSTANCE_TYPE="$2"
                shift 2
                ;;
            -u|--user)
                VSCODE_USER="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "不明なオプション: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # デフォルトスタック名
    if [[ -z "$STACK_NAME" ]]; then
        STACK_NAME="vscode-server-$USER_NAME"
    fi

    if [[ -z "$COMMAND" ]]; then
        log_error "コマンドが指定されていません"
        show_help
        exit 1
    fi
}

# AWS CLI確認
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLIがインストールされていません"
        exit 1
    fi

    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS認証が設定されていません"
        exit 1
    fi
}

# テンプレートファイル確認
check_template() {
    if [[ ! -f "$TEMPLATE_FILE" ]]; then
        log_error "テンプレートファイルが見つかりません: $TEMPLATE_FILE"
        exit 1
    fi
}

# スタック作成
create_stack() {
    log_info "🚀 VS Code Serverスタックを作成中..."
    log_info "スタック名: $STACK_NAME"
    log_info "リージョン: $REGION"
    log_info "インスタンスタイプ: $INSTANCE_TYPE"
    log_info "VS Codeユーザー: $VSCODE_USER"

    check_template

    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --parameters \
            "ParameterKey=VSCodeServerUser,ParameterValue=$VSCODE_USER" \
            "ParameterKey=InstanceType,ParameterValue=$INSTANCE_TYPE" \
            "ParameterKey=InstanceName,ParameterValue=$STACK_NAME" \
        --capabilities CAPABILITY_IAM \
        --region "$REGION"

    log_success "スタック作成を開始しました"
    log_info "📊 進捗を監視するには: $0 monitor -n $STACK_NAME -r $REGION"
    log_info "⏱️  作成完了まで約10-15分かかります"
}

# スタック状態確認
check_status() {
    local status
    status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")

    if [[ "$status" == "NOT_FOUND" ]]; then
        log_error "スタックが見つかりません: $STACK_NAME"
        return 1
    fi

    log_info "📊 スタック状態: $status"

    case "$status" in
        CREATE_COMPLETE)
            log_success "✅ スタック作成完了"
            show_quick_info
            ;;
        CREATE_IN_PROGRESS)
            log_info "🔄 スタック作成中..."
            show_creation_progress
            ;;
        CREATE_FAILED)
            log_error "❌ スタック作成失敗"
            show_errors
            ;;
        DELETE_IN_PROGRESS)
            log_info "🗑️  スタック削除中..."
            ;;
        DELETE_COMPLETE)
            log_success "✅ スタック削除完了"
            ;;
        *)
            log_warning "⚠️  スタック状態: $status"
            ;;
    esac

    return 0
}

# 作成進捗表示
show_creation_progress() {
    log_info "📈 作成進捗の詳細:"
    aws cloudformation describe-stack-events \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'StackEvents[?ResourceStatus==`CREATE_IN_PROGRESS`] | [0:5].[Timestamp,LogicalResourceId,ResourceStatus]' \
        --output table 2>/dev/null || log_warning "進捗情報を取得できませんでした"
}

# 進捗監視
monitor_stack() {
    log_info "📊 スタック進捗を監視中: $STACK_NAME"
    log_info "Ctrl+C で監視を終了"

    local start_time=$(date +%s)

    while true; do
        local status
        status=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].StackStatus' \
            --output text 2>/dev/null || echo "NOT_FOUND")

        if [[ "$status" == "NOT_FOUND" ]]; then
            log_error "スタックが見つかりません"
            break
        fi

        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        local elapsed_min=$((elapsed / 60))
        local elapsed_sec=$((elapsed % 60))

        echo -ne "\r$(date '+%H:%M:%S') - Status: $status (経過時間: ${elapsed_min}m${elapsed_sec}s)"

        case "$status" in
            CREATE_COMPLETE)
                echo ""
                log_success "🎉 スタック作成完了!"
                show_quick_info
                break
                ;;
            DELETE_COMPLETE)
                echo ""
                log_success "✅ スタック削除完了"
                break
                ;;
            CREATE_FAILED|DELETE_FAILED|ROLLBACK_COMPLETE)
                echo ""
                log_error "❌ 操作失敗: $status"
                show_errors
                break
                ;;
        esac

        sleep 5
    done
}

# クイック情報表示
show_quick_info() {
    echo ""
    log_success "🎯 VS Code Server準備完了!"
    echo ""

    local vscode_url password
    vscode_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`URL`].OutputValue' \
        --output text 2>/dev/null)

    password=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`Password`].OutputValue' \
        --output text 2>/dev/null)

    if [[ -n "$vscode_url" && "$vscode_url" != "None" ]]; then
        log_vscode "🌐 VS Code Server URL:"
        echo "   $vscode_url"
        echo ""
    fi

    if [[ -n "$password" && "$password" != "None" ]]; then
        log_info "🔑 接続トークン:"
        echo "   $password"
        echo ""
        log_info "💡 アクセス方法:"
        echo "   1. ブラウザでURLにアクセス"
        echo "   2. トークン入力画面で上記トークンを入力"
        echo "   3. または直接: ${vscode_url%\?*}?tkn=$password"
        echo ""
    fi

    log_info "📋 次のステップ:"
    echo "   1. $0 open -n $STACK_NAME      # ブラウザでオープン"
    echo "   2. $0 connect -n $STACK_NAME   # SSMでEC2に接続"
    echo "   3. 上記URLにアクセスしてVS Code Serverを使用"
    echo ""
}

# 出力値表示
show_outputs() {
    log_info "📋 スタック出力値:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table 2>/dev/null || log_warning "出力値を取得できませんでした"
}

# EC2インスタンスに接続
connect_to_instance() {
    log_info "🔌 EC2インスタンスに接続中..."

    # インスタンスIDを取得
    local instance_id
    instance_id=$(aws cloudformation describe-stack-resources \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --logical-resource-id VSCodeServerInstance \
        --query 'StackResources[0].PhysicalResourceId' \
        --output text 2>/dev/null)

    if [[ -z "$instance_id" || "$instance_id" == "None" ]]; then
        log_error "インスタンスIDを取得できませんでした"
        return 1
    fi

    log_info "インスタンスID: $instance_id"
    log_info "ユーザー: $VSCODE_USER"
    log_info "Session Manager Pluginが必要です"
    echo ""

    # SSM Session Manager で接続
    aws ssm start-session \
        --target "$instance_id" \
        --region "$REGION"
}

# ブラウザでオープン
open_browser() {
    local vscode_url
    vscode_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`URL`].OutputValue' \
        --output text 2>/dev/null)

    if [[ -z "$vscode_url" || "$vscode_url" == "None" ]]; then
        log_error "VS Code Server URLを取得できませんでした"
        return 1
    fi

    log_vscode "🌐 VS Code Serverをブラウザでオープン中..."
    log_info "URL: $vscode_url"

    # OS判定してブラウザオープン
    case "$(uname -s)" in
        Darwin)
            open "$vscode_url"
            ;;
        Linux)
            if command -v xdg-open > /dev/null; then
                xdg-open "$vscode_url"
            else
                log_warning "ブラウザを自動オープンできません。手動で以下のURLにアクセスしてください:"
                echo "$vscode_url"
            fi
            ;;
        CYGWIN*|MINGW32*|MSYS*|MINGW*)
            start "$vscode_url"
            ;;
        *)
            log_warning "ブラウザを自動オープンできません。手動で以下のURLにアクセスしてください:"
            echo "$vscode_url"
            ;;
    esac
}

# エラー表示
show_errors() {
    log_error "❌ 最新のエラーイベント:"
    aws cloudformation describe-stack-events \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`] | [0:5].[Timestamp,LogicalResourceId,ResourceStatusReason]' \
        --output table 2>/dev/null || log_warning "エラー情報を取得できませんでした"
}

# ログ表示
show_logs() {
    log_info "📜 CloudFormationイベントログ (最新10件):"
    aws cloudformation describe-stack-events \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'StackEvents[0:10].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
        --output table 2>/dev/null || log_warning "ログを取得できませんでした"
}

# スタック削除
delete_stack() {
    log_warning "⚠️  スタックを削除します: $STACK_NAME"
    log_warning "これにより以下が削除されます:"
    echo "   • EC2インスタンス"
    echo "   • CloudFront Distribution"
    echo "   • セキュリティグループ"
    echo "   • 全ての関連リソース"
    echo ""

    read -p "本当に削除しますか? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "削除をキャンセルしました"
        return 0
    fi

    aws cloudformation delete-stack \
        --stack-name "$STACK_NAME" \
        --region "$REGION"

    log_success "🗑️  スタック削除を開始しました"
    log_info "📊 進捗を監視するには: $0 monitor -n $STACK_NAME -r $REGION"
}

# スタック一覧
list_stacks() {
    log_info "📋 VS Code Serverスタック一覧 (リージョン: $REGION):"
    aws cloudformation list-stacks \
        --region "$REGION" \
        --stack-status-filter CREATE_COMPLETE CREATE_IN_PROGRESS UPDATE_COMPLETE DELETE_IN_PROGRESS \
        --query 'StackSummaries[?contains(StackName, `vscode`) || contains(StackName, `server`)].[StackName,StackStatus,CreationTime]' \
        --output table
}

# テンプレート検証
validate_template() {
    check_template
    log_info "🔍 テンプレートを検証中: $TEMPLATE_FILE"

    if aws cloudformation validate-template \
        --template-body "file://$TEMPLATE_FILE" \
        --region "$REGION" > /dev/null; then
        log_success "✅ テンプレート検証成功"
    else
        log_error "❌ テンプレート検証失敗"
        return 1
    fi
}

# メイン処理
main() {
    parse_args "$@"
    check_aws_cli

    case "$COMMAND" in
        create)
            create_stack
            ;;
        status)
            check_status
            ;;
        monitor)
            monitor_stack
            ;;
        outputs)
            show_outputs
            ;;
        connect)
            connect_to_instance
            ;;
        open)
            open_browser
            ;;
        logs)
            show_logs
            ;;
        delete)
            delete_stack
            ;;
        list)
            list_stacks
            ;;
        validate)
            validate_template
            ;;
        *)
            log_error "不明なコマンド: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# スクリプト実行
main "$@"