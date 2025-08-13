# How to use

```bash
$ bash stack-manager.sh create -e xxx -p MyPassword123
[INFO] 🚀 VS Code Workshopスタックを作成中...
[INFO] スタック名: vscode-workshop-coder
[INFO] リージョン: us-east-1
[INFO] インスタンスタイプ: c7i.4xlarge
[COGNITO] 管理者メール: xxx
[INFO] パスワード: [HIDDEN]
{
    "StackId": "arn:aws:cloudformation:us-east-1:xxx:stack/vscode-workshop-coder/b5523e50-7543-11f0-a56a-124d3fdcb0b3"
}
[SUCCESS] スタック作成を開始しました
[INFO] 📊 進捗を監視するには: stack-manager.sh monitor -n vscode-workshop-coder -r us-east-1
[INFO] ⏱️  作成完了まで約5-10分かかります

$ bash  stack-manager.sh monitor -n vscode-workshop-coder -r us-east-1
[INFO] 📊 スタック進捗を監視中: vscode-workshop-coder
[INFO] Ctrl+C で監視を終了
17:15:50 - Status: CREATE_COMPLETE (経過時間: 5m36s)0s)
[SUCCESS] 🎉 スタック作成完了!

[SUCCESS] 🎯 ワークショップ準備完了!

[VSCODE] 🌐 VS Code Server URL:
   https://xxxx.cloudfront.net/?folder=/workshop

[INFO] 📋 次のステップ:
   1. stack-manager.sh login -n vscode-workshop-coder     # ログイン情報を確認
   2. stack-manager.sh open -n vscode-workshop-coder      # ブラウザでオープン
   3. 上記URLにアクセスしてログイン


$ bash stack-manager.sh login -n vscode-workshop-coder
[COGNITO] 🔑 ログイン情報:
Email: xxx
Password: MyPassword123

[VSCODE] 🌐 アクセスURL:
   https://xxxx.cloudfront.net/?folder=/workshop

[COGNITO] 🔗 直接CognitoログインURL:
   https://vscode-workshop-coder-workshop-xxxxx.auth.us-east-1.amazoncognito.com/oauth2/authorize?client_id=xxxxx&response_type=code&scope=openid+email+profile&redirect_uri=https://xxxx.cloudfront.net/oauth/callback

[INFO] 💡 ブラウザでオープンするには: stack-manager.sh open -n vscode-workshop-coder

$ bash stack-manager.sh open -n vscode-workshop-coder
[VSCODE] 🌐 VS Code Serverをブラウザでオープン中...
[INFO] URL: https://xxxx.cloudfront.net/?folder=/workshop
[WARNING] ブラウザを自動オープンできません。手動で以下のURLにアクセスしてください:
https://xxxx.cloudfront.net/?folder=/workshop
```