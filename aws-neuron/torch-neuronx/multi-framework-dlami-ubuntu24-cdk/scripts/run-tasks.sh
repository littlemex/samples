#!/bin/bash
# 汎用タスクランナー - JSONタスク定義を実行
# 冪等性を保ち、失敗箇所から再開可能

set -e

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ヘルプ表示
usage() {
    cat << EOF
汎用タスクランナー - JSONタスク定義を実行

使用方法: $0 [OPTIONS]

Options:
    -i, --instance-id ID        対象のEC2インスタンスID (必須)
    -r, --region REGION         AWSリージョン (デフォルト: sa-east-1)
    -f, --task-file FILE        タスク定義JSONファイル (必須)
    -v, --variables JSON        変数定義（JSON形式）
    -s, --start-from TASK_ID    指定したタスクIDから再開
    --state-file FILE           状態ファイルのパス（デフォルト: /tmp/task-state-<instance-id>.json）
    --clean-state               状態ファイルをクリーンして最初から実行
    --dry-run                   実際には実行せず、タスクを表示のみ
    -h, --help                  このヘルプを表示

例:
    # 基本的な使用方法
    $0 -i i-1234567890abcdef0 -f tasks/code-server-setup.json

    # 変数を指定
    $0 -i i-1234567890abcdef0 -f tasks/code-server-setup.json \\
       -v '{"USER":"developer","PASSWORD":"secret123"}'

    # 特定のタスクから再開
    $0 -i i-1234567890abcdef0 -f tasks/code-server-setup.json \\
       -s 03-install-code-server

    # ドライラン（実行内容の確認）
    $0 -i i-1234567890abcdef0 -f tasks/code-server-setup.json --dry-run
EOF
}

# デフォルト値
INSTANCE_ID=""
REGION="sa-east-1"
TASK_FILE=""
VARIABLES_JSON="{}"
START_FROM=""
STATE_FILE=""
CLEAN_STATE=false
DRY_RUN=false

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
        -f|--task-file)
            TASK_FILE="$2"
            shift 2
            ;;
        -v|--variables)
            VARIABLES_JSON="$2"
            shift 2
            ;;
        -s|--start-from)
            START_FROM="$2"
            shift 2
            ;;
        --state-file)
            STATE_FILE="$2"
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
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}エラー: 不明なオプション: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# 必須パラメータチェック
if [[ -z "$INSTANCE_ID" ]]; then
    echo -e "${RED}エラー: インスタンスIDが指定されていません${NC}"
    usage
    exit 1
fi

if [[ -z "$TASK_FILE" ]]; then
    echo -e "${RED}エラー: タスクファイルが指定されていません${NC}"
    usage
    exit 1
fi

if [[ ! -f "$TASK_FILE" ]]; then
    echo -e "${RED}エラー: タスクファイルが見つかりません: $TASK_FILE${NC}"
    exit 1
fi

# 状態ファイルのデフォルト設定
if [[ -z "$STATE_FILE" ]]; then
    STATE_FILE="/tmp/task-state-${INSTANCE_ID}.json"
fi

# 状態ファイルのクリーン
if [[ "$CLEAN_STATE" == true ]] && [[ -f "$STATE_FILE" ]]; then
    echo -e "${YELLOW}状態ファイルをクリーンします: $STATE_FILE${NC}"
    rm -f "$STATE_FILE"
fi

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}汎用タスクランナー${NC}"
echo -e "${BLUE}=========================================${NC}"
echo "インスタンスID: $INSTANCE_ID"
echo "リージョン: $REGION"
echo "タスクファイル: $TASK_FILE"
echo "状態ファイル: $STATE_FILE"
if [[ "$DRY_RUN" == true ]]; then
    echo -e "${YELLOW}モード: ドライラン${NC}"
fi
echo -e "${BLUE}=========================================${NC}"
echo ""

# 環境変数をエクスポート（Pythonスクリプトから参照可能にする）
export INSTANCE_ID
export REGION
export TASK_FILE
export VARIABLES_JSON
export START_FROM
export STATE_FILE
export DRY_RUN

# タスク実行
python3 << 'PYTHON_EOF'
import json
import subprocess
import sys
import time
import os
from datetime import datetime

# パラメータ取得
instance_id = os.environ.get('INSTANCE_ID')
region = os.environ.get('REGION')
task_file = os.environ.get('TASK_FILE')
variables_json = os.environ.get('VARIABLES_JSON', '{}')
start_from = os.environ.get('START_FROM', '')
state_file = os.environ.get('STATE_FILE')
dry_run = os.environ.get('DRY_RUN', 'false') == 'true'

# 色定義
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
CYAN = '\033[0;36m'
NC = '\033[0m'

def log_info(msg):
    print(f"{BLUE}[INFO]{NC} {msg}")

def log_success(msg):
    print(f"{GREEN}[SUCCESS]{NC} {msg}")

def log_warning(msg):
    print(f"{YELLOW}[WARNING]{NC} {msg}")

def log_error(msg):
    print(f"{RED}[ERROR]{NC} {msg}")

def log_task(msg):
    print(f"{CYAN}[TASK]{NC} {msg}")

# タスク定義読み込み
log_info(f"タスク定義を読み込み中: {task_file}")
with open(task_file, 'r') as f:
    task_definition = json.load(f)

# 変数読み込み
user_variables = json.loads(variables_json)

# タスク定義の変数とマージ（ユーザー指定が優先）
variables = task_definition.get('variables', {})
variables.update(user_variables)

log_info(f"タスク名: {task_definition.get('name', 'Unnamed')}")
log_info(f"説明: {task_definition.get('description', 'No description')}")
log_info(f"タスク数: {len(task_definition['tasks'])}")
print("")

# 状態ファイル読み込み
state = {}
if os.path.exists(state_file):
    log_info(f"既存の状態ファイルを読み込み: {state_file}")
    with open(state_file, 'r') as f:
        state = json.load(f)
    print(f"  完了済みタスク: {len([t for t in state.get('tasks', {}).values() if t.get('status') == 'success'])}")
    print(f"  失敗したタスク: {len([t for t in state.get('tasks', {}).values() if t.get('status') == 'failed'])}")
    print("")

# 状態初期化
if 'tasks' not in state:
    state['tasks'] = {}
if 'last_run' not in state:
    state['last_run'] = None

# 変数置換関数
def replace_variables(text, variables):
    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text

# SSM send-command実行関数
def execute_task(task_id, commands):
    """タスクを実行"""
    log_task(f"タスクを実行中: {task_id}")

    # コマンドを結合
    script = '\n'.join(commands)

    if dry_run:
        print(f"{YELLOW}[DRY-RUN] 実行するコマンド:{NC}")
        print("---")
        print(script)
        print("---")
        return {
            'status': 'success',
            'command_id': 'DRY-RUN',
            'output': 'Dry run - not executed'
        }

    # 一時ファイルに保存
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
        f.write(script)
        script_file = f.name

    try:
        # JSON構築
        params = {
            "InstanceIds": [instance_id],
            "DocumentName": "AWS-RunShellScript",
            "Parameters": {
                "commands": [script]
            }
        }

        # SSM send-command実行
        result = subprocess.run(
            ['aws', 'ssm', 'send-command', '--region', region, '--cli-input-json', json.dumps(params), '--output', 'json'],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            log_error(f"SSM send-command失敗: {result.stderr}")
            return {
                'status': 'failed',
                'error': result.stderr
            }

        command_data = json.loads(result.stdout)
        command_id = command_data['Command']['CommandId']

        log_info(f"コマンドID: {command_id}")
        log_info("実行完了を待機中...")

        # 完了待機
        max_wait = 300  # 5分
        wait_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(wait_interval)
            elapsed += wait_interval

            # ステータス確認
            status_result = subprocess.run(
                ['aws', 'ssm', 'get-command-invocation',
                 '--command-id', command_id,
                 '--instance-id', instance_id,
                 '--region', region,
                 '--output', 'json'],
                capture_output=True,
                text=True
            )

            if status_result.returncode == 0:
                invocation = json.loads(status_result.stdout)
                status = invocation.get('Status', 'Pending')

                if status == 'Success':
                    output = invocation.get('StandardOutputContent', '')
                    log_success(f"タスク完了: {task_id}")
                    return {
                        'status': 'success',
                        'command_id': command_id,
                        'output': output
                    }
                elif status in ['Failed', 'Cancelled', 'TimedOut']:
                    error = invocation.get('StandardErrorContent', '')
                    log_error(f"タスク失敗: {task_id}")
                    print(f"エラー出力:\n{error}")
                    return {
                        'status': 'failed',
                        'command_id': command_id,
                        'error': error
                    }
                else:
                    print(f"  ステータス: {status} (経過時間: {elapsed}秒)")

        log_error(f"タイムアウト: {task_id}")
        return {
            'status': 'failed',
            'command_id': command_id,
            'error': 'Timeout waiting for command completion'
        }

    finally:
        # 一時ファイル削除
        if os.path.exists(script_file):
            os.unlink(script_file)

# タスク実行
start_execution = not start_from
total_tasks = len(task_definition['tasks'])
completed_tasks = 0
failed_tasks = 0

for idx, task in enumerate(task_definition['tasks'], 1):
    task_id = task['id']
    task_name = task.get('name', task_id)
    task_desc = task.get('description', '')

    # 開始タスクまでスキップ
    if not start_execution:
        if task_id == start_from:
            start_execution = True
            log_info(f"タスク '{task_id}' から再開します")
        else:
            log_info(f"[{idx}/{total_tasks}] スキップ: {task_id} - {task_name}")
            continue

    # 既に成功しているタスクはスキップ
    if task_id in state['tasks'] and state['tasks'][task_id].get('status') == 'success':
        log_success(f"[{idx}/{total_tasks}] 完了済み: {task_id} - {task_name}")
        completed_tasks += 1
        continue

    print("")
    print(f"{CYAN}{'='*80}{NC}")
    log_task(f"[{idx}/{total_tasks}] {task_id}")
    print(f"  名前: {task_name}")
    print(f"  説明: {task_desc}")
    print(f"{CYAN}{'='*80}{NC}")

    # コマンド準備
    commands = task.get('commands', [])
    replaced_commands = [replace_variables(cmd, variables) for cmd in commands]

    # タスク実行
    result = execute_task(task_id, replaced_commands)

    # 状態更新
    state['tasks'][task_id] = {
        'name': task_name,
        'status': result['status'],
        'timestamp': datetime.now().isoformat(),
        'command_id': result.get('command_id', ''),
    }

    if result['status'] == 'success':
        completed_tasks += 1
        if not dry_run and result.get('output'):
            print(f"\n{GREEN}出力:{NC}")
            print(result['output'][:500])  # 最初の500文字のみ表示
    else:
        failed_tasks += 1
        state['tasks'][task_id]['error'] = result.get('error', '')

    # 状態ファイル保存
    state['last_run'] = datetime.now().isoformat()
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

    # 失敗時は停止
    if result['status'] == 'failed' and not dry_run:
        log_error("タスク実行失敗により停止します")
        log_info(f"再開するには: --start-from {task_id}")
        sys.exit(1)

# サマリー表示
print("")
print(f"{GREEN}{'='*80}{NC}")
print(f"{GREEN}タスク実行完了{NC}")
print(f"{GREEN}{'='*80}{NC}")
print(f"総タスク数: {total_tasks}")
print(f"完了: {completed_tasks}")
print(f"失敗: {failed_tasks}")
print(f"スキップ: {total_tasks - completed_tasks - failed_tasks}")
print(f"状態ファイル: {state_file}")
print(f"{GREEN}{'='*80}{NC}")

if failed_tasks == 0:
    sys.exit(0)
else:
    sys.exit(1)

PYTHON_EOF

exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    echo ""
    echo -e "${GREEN}✅ 全てのタスクが正常に完了しました${NC}"
else
    echo ""
    echo -e "${RED}❌ タスク実行中にエラーが発生しました${NC}"
fi

exit $exit_code
