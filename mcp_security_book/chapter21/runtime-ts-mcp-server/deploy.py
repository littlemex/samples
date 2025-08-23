#!/usr/bin/env python3
"""
MCP Server デプロイメントスクリプト
Amazon Bedrock AgentCore 上に TypeScript MCP Server をデプロイするための自動化スクリプト

使用方法:
    python deploy_mcp_server.py --step1  # Cognito 設定
    python deploy_mcp_server.py --step2  # IAM ロール作成
    python deploy_mcp_server.py --step5  # 設定保存
    python deploy_mcp_server.py --all    # 全ステップ実行
"""

import argparse
import sys
import os
import json
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# 現在のディレクトリを取得
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

try:
    from utils import create_agentcore_role, setup_cognito_user_pool
    import boto3
    from boto3.session import Session
except ImportError as e:
    print(f"エラー: 必要なモジュールがインポートできません: {e}")
    print("boto3 と utils.py が利用可能か確認してください。")
    sys.exit(1)


class MCPServerDeployer:
    """MCP Server デプロイメント管理クラス"""
    
    def __init__(self):
        # 環境変数からAWS設定を取得
        aws_region = os.getenv('AWS_REGION')
        aws_profile = os.getenv('AWS_PROFILE')
        
        # boto3セッションを作成（環境変数を優先）
        session_params = {}
        if aws_region:
            session_params['region_name'] = aws_region
            print(f"  AWS_REGION: {aws_region} (環境変数から)")
        if aws_profile:
            session_params['profile_name'] = aws_profile
            print(f"  AWS_PROFILE: {aws_profile} (環境変数から)")
        
        self.boto_session = Session(**session_params)
        self.region = self.boto_session.region_name or aws_region or 'us-east-1'
        
        if not aws_region and self.boto_session.region_name:
            print(f"  AWS_REGION: {self.boto_session.region_name} (boto3デフォルト)")
        
        self.config_file = current_dir / "deployment_config.json"
        self.config = self.load_config()
        
    def load_config(self):
        """保存された設定を読み込む"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_config(self):
        """設定をファイルに保存"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def step1_setup_cognito(self):
        """ステップ 1: Amazon Cognito ユーザープールの設定"""
        print("\n=== ステップ 1: Amazon Cognito 設定 ===")
        print("Amazon Cognito ユーザープールを設定中...")
        
        try:
            cognito_config = setup_cognito_user_pool()
            print("✓ Cognito 設定完了")
            print(f"  ユーザープール ID: {cognito_config.get('user_pool_id', 'N/A')}")
            print(f"  Client ID: {cognito_config.get('client_id', 'N/A')}")
            print(f"  Discovery URL: {cognito_config.get('discovery_url', 'N/A')}")
            
            # 設定を保存
            self.config['cognito'] = cognito_config
            self.save_config()
            
            return True
        except Exception as e:
            print(f"❌ Cognito 設定エラー: {e}")
            return False
    
    def step2_create_iam_role(self):
        """ステップ 2: IAM 実行ロールの作成"""
        print("\n=== ステップ 2: IAM ロール作成 ===")
        
        tool_name = "mcp_server_ac"
        print(f"{tool_name} 用の IAM ロールを作成中...")
        
        try:
            agentcore_iam_role = create_agentcore_role(agent_name=tool_name)
            print("✓ IAM ロール作成完了")
            print(f"  ロール ARN: {agentcore_iam_role['Role']['Arn']}")
            
            # 設定を保存
            self.config['iam_role'] = {
                'role_name': agentcore_iam_role['Role']['RoleName'],
                'role_arn': agentcore_iam_role['Role']['Arn']
            }
            self.save_config()
            
            return True
        except Exception as e:
            print(f"❌ IAM ロール作成エラー: {e}")
            return False
    
    def step3_local_development(self):
        """ステップ 3: ローカル開発環境のセットアップ（情報表示のみ）"""
        print("\n=== ステップ 3: MCP Server の作成 ===")
        print("以下の手順でローカル開発を行ってください:")
        print("\n1. 依存関係のインストールと build:")
        print("   npm install && npm run build")
        print("\n2. Server の起動（ローカル実行）:")
        print("   PORT=13000 npm run start")
        print("\n3. MCP インスペクターでのテスト(ローカル PC で実行):")
        print("   npx @modelcontextprotocol/inspector")
        return True
    
    def step4_docker_deployment(self):
        """ステップ 4: Docker デプロイメント（自動実行）"""
        print("\n=== ステップ 4: Docker 経由での MCP Server デプロイメント ===")
        
        try:
            # AWS アカウントIDを取得
            sts_client = boto3.client("sts")
            account_id = sts_client.get_caller_identity()["Account"]
            ecr_uri = f"{account_id}.dkr.ecr.{self.region}.amazonaws.com"
            repository_name = "mcp-server"
            image_uri = f"{ecr_uri}/{repository_name}:latest"
            
            print(f"AWS アカウント ID: {account_id}")
            print(f"リージョン: {self.region}")
            
            # 1. ECR リポジトリの作成
            print("\n1. ECR リポジトリの作成...")
            ecr_client = boto3.client('ecr', region_name=self.region)
            try:
                response = ecr_client.create_repository(
                    repositoryName=repository_name,
                    imageScanningConfiguration={'scanOnPush': True}
                )
                print(f"✓ ECR リポジトリを作成しました: {repository_name}")
                print(f"  リポジトリ URI: {response['repository']['repositoryUri']}")
            except ecr_client.exceptions.RepositoryAlreadyExistsException:
                print(f"✓ ECR リポジトリは既に存在します: {repository_name}")
            
            # 2. Docker ログイン
            print("\n2. ECR へのログイン...")
            login_cmd = f"aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {ecr_uri}"
            result = subprocess.run(login_cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print("✓ ECR へのログインに成功しました")
            else:
                print(f"❌ ECR ログインエラー: {result.stderr}")
                return False
            
            # 3. Docker イメージのビルドとプッシュ
            print("\n3. Docker イメージのビルドとプッシュ...")
            print("  ビルド中... (数分かかる場合があります)")
            
            # マルチプラットフォームビルドのためのビルダーを作成
            builder_name = "mcp-server-builder"
            create_builder_cmd = f"docker buildx create --name {builder_name} --use"
            subprocess.run(create_builder_cmd, shell=True, capture_output=True)
            
            # ビルドとプッシュ
            build_cmd = f"docker buildx build --platform linux/arm64 -t {image_uri} --push ."
            result = subprocess.run(build_cmd, shell=True, capture_output=True, text=True, cwd=current_dir)
            
            if result.returncode == 0:
                print(f"✓ Docker イメージをビルドしてプッシュしました: {image_uri}")
            else:
                print(f"❌ Docker ビルドエラー: {result.stderr}")
                # ビルダーをクリーンアップ
                subprocess.run(f"docker buildx rm {builder_name}", shell=True, capture_output=True)
                return False
            
            # ビルダーをクリーンアップ
            subprocess.run(f"docker buildx rm {builder_name}", shell=True, capture_output=True)
            
            # 設定を保存
            self.config['docker'] = {
                'repository_name': repository_name,
                'image_uri': image_uri,
                'ecr_uri': ecr_uri
            }
            self.save_config()
            
            # 4. デプロイ手順の表示
            print("\n4. Bedrock AgentCore へのデプロイ:")
            print("   以下の情報を使用して AWS コンソールでデプロイを完了してください：")
            print("\n   ① AWS コンソール → Bedrock → AgentCore → エージェントの作成")
            print("   ② プロトコル: MCP を選択")
            print("   ③ エージェントランタイムの設定:")
            print(f"      - イメージ URI: {image_uri}")
            
            if 'cognito' in self.config:
                print(f"      - Discovery URL: {self.config['cognito'].get('discovery_url', 'N/A')}")
                print(f"      - Client ID: {self.config['cognito'].get('client_id', 'N/A')}")
            
            if 'iam_role' in self.config:
                print(f"      - 実行ロール: {self.config['iam_role'].get('role_arn', 'N/A')}")
            
            print("\n⚠️  重要: デプロイ完了後、エージェント ARN をメモしてください。")
            print("   次のコマンドでステップ 5 を実行する際に必要です：")
            print(f"   python {Path(__file__).name} --step5 --agent-arn <YOUR_AGENT_ARN>")
            
            return True
            
        except Exception as e:
            print(f"❌ Docker デプロイメントエラー: {e}")
            return False
    
    def step5_save_configuration(self, agent_arn=None):
        """ステップ 5: リモートアクセス用の設定保存"""
        print("\n=== ステップ 5: 設定の保存 ===")
        
        if not agent_arn:
            print("❌ エラー: エージェント ARN が指定されていません。")
            print("使用方法: python deploy_mcp_server.py --step5 --agent-arn <YOUR_AGENT_ARN>")
            return False
        
        if 'cognito' not in self.config:
            print("❌ エラー: Cognito 設定が見つかりません。先にステップ 1 を実行してください。")
            return False
        
        ssm_client = boto3.client('ssm', region_name=self.region)
        secrets_client = boto3.client('secretsmanager', region_name=self.region)
        
        try:
            # Cognito 認証情報を Secrets Manager に保存
            secret_name = 'mcp_server/cognito/credentials'
            try:
                secrets_client.create_secret(
                    Name=secret_name,
                    Description='MCP Server 用の Cognito 認証情報',
                    SecretString=json.dumps(self.config['cognito'])
                )
                print(f"✓ Cognito 認証情報を Secrets Manager に保存しました")
            except secrets_client.exceptions.ResourceExistsException:
                secrets_client.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(self.config['cognito'])
                )
                print(f"✓ Cognito 認証情報を Secrets Manager で更新しました")
            
            # エージェント ARN を Parameter Store に保存
            param_name = '/mcp_server/runtime/agent_arn'
            ssm_client.put_parameter(
                Name=param_name,
                Value=agent_arn,
                Type='String',
                Description='MCP Server 用のエージェント ARN',
                Overwrite=True
            )
            print(f"✓ エージェント ARN を Parameter Store に保存しました")
            print(f"  パラメータ名: {param_name}")
            print(f"  値: {agent_arn}")
            
            # 設定を保存
            self.config['agent_arn'] = agent_arn
            self.save_config()
            
            return True
        except Exception as e:
            print(f"❌ 設定保存エラー: {e}")
            return False
    
    def step6_test_connection(self):
        """ステップ 6: 接続テスト"""
        print("\n=== ステップ 6: 接続テスト ===")
        print("以下のコマンドで接続をテストできます：")
        print("\n基本的な接続テスト:")
        print("  python my_mcp_client_remote.py")
        print("\nツール呼び出しテスト:")
        print("  python invoke_mcp_tools.py")
        return True
    
    def run_all_steps(self, agent_arn=None):
        """全ステップを順番に実行"""
        print("=== 全ステップを実行します ===")
        
        # ステップ 1
        if not self.step1_setup_cognito():
            print("ステップ 1 で失敗しました。")
            return False
        
        # ステップ 2
        if not self.step2_create_iam_role():
            print("ステップ 2 で失敗しました。")
            return False
        
        # ステップ 3（情報表示のみ）
        self.step3_local_development()
        
        # ステップ 4（自動実行）
        if not self.step4_docker_deployment():
            print("ステップ 4 で失敗しました。")
            return False
        
        # ステップ 5（agent_arn が指定されている場合のみ）
        if agent_arn:
            if not self.step5_save_configuration(agent_arn):
                print("ステップ 5 で失敗しました。")
                return False
        else:
            print("\n⚠️  注意: エージェント ARN が指定されていないため、ステップ 5 はスキップされました。")
            print("デプロイ後に以下のコマンドを実行してください：")
            print("python deploy_mcp_server.py --step5 --agent-arn <YOUR_AGENT_ARN>")
        
        # ステップ 6（情報表示のみ）
        self.step6_test_connection()
        
        print("\n✅ 処理が完了しました！")
        return True
    
    def show_status(self):
        """現在の設定状態を表示"""
        print("\n=== 現在の設定状態 ===")
        
        if 'cognito' in self.config:
            print("\n✓ Cognito 設定:")
            print(f"  ユーザープール ID: {self.config['cognito'].get('user_pool_id', 'N/A')}")
            print(f"  Client ID: {self.config['cognito'].get('client_id', 'N/A')}")
        else:
            print("\n❌ Cognito 設定: 未設定")
        
        if 'iam_role' in self.config:
            print("\n✓ IAM ロール:")
            print(f"  ロール名: {self.config['iam_role'].get('role_name', 'N/A')}")
            print(f"  ロール ARN: {self.config['iam_role'].get('role_arn', 'N/A')}")
        else:
            print("\n❌ IAM ロール: 未作成")
        
        if 'docker' in self.config:
            print("\n✓ Docker 設定:")
            print(f"  リポジトリ名: {self.config['docker'].get('repository_name', 'N/A')}")
            print(f"  イメージ URI: {self.config['docker'].get('image_uri', 'N/A')}")
        else:
            print("\n❌ Docker 設定: 未設定")
        
        if 'agent_arn' in self.config:
            print(f"\n✓ エージェント ARN: {self.config['agent_arn']}")
        else:
            print("\n❌ エージェント ARN: 未設定")


def main():
    # .env ファイルを読み込む
    env_file = current_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ 環境変数を .env ファイルから読み込みました: {env_file}")
    else:
        print("⚠️  .env ファイルが見つかりません。環境変数は既存の設定を使用します。")
    
    parser = argparse.ArgumentParser(
        description='MCP Server を Amazon Bedrock AgentCore にデプロイするための自動化スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  uv run deploy.py --step1              # Cognito 設定
  uv run deploy.py --step2              # IAM ロール作成
  uv run deploy.py --step3              # ローカル開発手順を表示
  uv run deploy.py --step4              # Docker ビルドと ECR プッシュ（自動実行）
  uv run deploy.py --step5 --agent-arn arn:aws:...  # 設定保存
  uv run deploy.py --step6              # テスト手順を表示
  uv run deploy.py --all                # 全ステップ実行
  uv run deploy.py --status             # 現在の設定状態を表示
        """
    )
    
    # ステップオプション
    parser.add_argument('--step1', action='store_true', 
                       help='ステップ 1: Amazon Cognito ユーザープールの設定')
    parser.add_argument('--step2', action='store_true', 
                       help='ステップ 2: IAM 実行ロールの作成')
    parser.add_argument('--step3', action='store_true', 
                       help='ステップ 3: ローカル開発手順を表示')
    parser.add_argument('--step4', action='store_true', 
                       help='ステップ 4: Docker イメージのビルドと ECR へのプッシュ（自動実行）')
    parser.add_argument('--step5', action='store_true', 
                       help='ステップ 5: リモートアクセス用の設定保存')
    parser.add_argument('--step6', action='store_true', 
                       help='ステップ 6: 接続テスト手順を表示')
    
    # その他のオプション
    parser.add_argument('--all', action='store_true', 
                       help='全ステップを順番に実行')
    parser.add_argument('--status', action='store_true', 
                       help='現在の設定状態を表示')
    parser.add_argument('--agent-arn', type=str, 
                       help='エージェント ARN（ステップ 5 で必要）')
    
    args = parser.parse_args()
    
    # 引数が何も指定されていない場合はヘルプを表示
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    # デプロイヤーインスタンスを作成
    deployer = MCPServerDeployer()
    
    # 各ステップの実行
    if args.status:
        deployer.show_status()
    elif args.all:
        deployer.run_all_steps(args.agent_arn)
    elif args.step1:
        deployer.step1_setup_cognito()
    elif args.step2:
        deployer.step2_create_iam_role()
    elif args.step3:
        deployer.step3_local_development()
    elif args.step4:
        deployer.step4_docker_deployment()
    elif args.step5:
        deployer.step5_save_configuration(args.agent_arn)
    elif args.step6:
        deployer.step6_test_connection()


if __name__ == "__main__":
    main()
