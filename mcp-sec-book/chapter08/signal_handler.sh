#!/bin/bash

echo "メインプロセス PID: $$"

# シグナルハンドラを設定しない場合、PID 1 ではシグナルが無視される

echo "ゾンビプロセス生成スクリプトを起動します..."
echo "このスクリプトは定期的にサブプロセスを生成し、その状態を表示します"
echo ""
echo "プロセスの状態は自動的に表示されます"
echo "コンテナを停止するには:"
echo "docker stop <container_id>"
echo ""

# zombie_maker.sh を実行（このスクリプトは無限ループで実行され続ける）
exec /zombie_maker.sh
