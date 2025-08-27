#!/usr/bin/env python3
"""
MCP Server デプロイメントスクリプト（ロール自動更新対応版）

Amazon Bedrock AgentCore 上に TypeScript MCP Server をデプロイするための自動化スクリプト

使用方法:
python deploy.py --step1  # Cognito 設定
python deploy.py --step2  # IAM ロール作成/更新
python deploy.py --step5  # 設定保存
python deploy.py --all    # 全ステップ実行
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# 現在のディレクトリを取得
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

try:
    import boto3
    from boto3.session import Session

    from utils import (
        reauthenticate_user,
        setup_cognito_user_pool,
        update_agentcore_role,
    )
except ImportError as e:
    print(f"エラー: 必要なモジュールがインポートできません: {e}")
    print("boto3 と utils.py が利用可能か確認してください。")
    sys.exit(1)


class MCPServerDeployer:
    """MCP Server デ
    プロイメント管理クラス（ロール自動更新対応）"""

    def __init__(self):
        # 環境変数からAWS設定を取得
        aws_region = os.getenv("AWS_REGION")
        aws_profile = os.getenv("AWS_PROFILE")

        # boto3セッションを作成（環境変数を優先）
        session_params = {}
        if aws_region:
            session_params["region_name"] = aws_region
            print(f"  AWS_REGION: {aws_region} (環境変数から)")
        if aws_profile:
            session_params["profile_name"] = aws_profile
            print(f"  AWS_PROFILE: {aws_profile} (環境変数から)")

        self.boto_session = Session(**session_params)
        self.region = self.boto_session.region_name or aws_region or "us-east-1"

        if not aws_region and self.boto_session.region_name:
            print(f"  AWS_REGION: {self.boto_session.region_name} (boto3デフォルト)")

        self.config_file = current_dir / "deployment_config.json"
        self.config = self.load_config()

    def load_config(self):
        """保存された設定を読み込む"""
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        """設定をファイルに保存"""
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)

    def update_token(self):
        """トークンのみを更新する"""
        print("\n=== トークン更新 ===")
        print("既存のCognitoユーザーを再認証して新しいトークンを取得中...")

        try:
            # 既存の設定からclient_idを取得
            if (
                "cognito" not in self.config
                or "client_id" not in self.config["cognito"]
            ):
                print(
                    "❌ エラー: Cognito設定が見つかりません。先にステップ1を実行してください。"
                )
                return False

            client_id = self.config["cognito"]["client_id"]
            print(f"  Client ID: {client_id}")

            # reauthenticate_user関数を呼び出して新しいトークンを取得
            bearer_token = reauthenticate_user(client_id)

            if not bearer_token:
                print("❌ トークン更新に失敗しました。")
                return False

            # 設定を更新
            self.config["cognito"]["bearer_token"] = bearer_token
            self.save_config()

            print("✓ トークン更新完了")
            print("  新しいトークンが生成され、設定に保存されました。")

            # トークン更新後にstep5を実行して設定を保存
            print("\n自動的にステップ5を実行して設定を保存します...")
            self.step5_save_configuration()

            return True

        except Exception as e:
            print(f"❌ トークン更新エラー: {e}")
            import traceback

            traceback.print_exc()
            return False

    def step1_setup_cognito(self):
        """ステップ 1: Amazon Cognito ユーザープールの設定"""
        print("\n=== ステップ 1: Amazon Cognito 設定 ===")
        print("Amazon Cognito ユーザープールを設定中...")

        try:
            cognito_config = setup_cognito_user_pool()
            print("✓ Cognito 設定完了")
            print(f"  ユーザープール ID: {cognito_config.get('pool_id', 'N/A')}")
            print(f"  Client ID: {cognito_config.get('client_id', 'N/A')}")
            print(f"  Discovery URL: {cognito_config.get('discovery_url', 'N/A')}")

            # 設定を保存
            self.config["cognito"] = cognito_config
            self.save_config()

            return True

        except Exception as e:
            print(f"❌ Cognito 設定エラー: {e}")
            return False

    def step2_create_iam_role(self):
        """ステップ 2: IAM 実行ロールの作成/更新（自動処理）"""
        print("\n=== ステップ 2: IAM ロール作成/更新 ===")
        tool_name = "mcp_server_ac"
        print(f"{tool_name} 用の IAM ロールを作成/更新中...")

        try:
            # 新しい update_agentcore_role 関数を使用
            agentcore_iam_role = update_agentcore_role(agent_name=tool_name)

            print("✓ IAM ロール処理完了")
            print(f"  ロール ARN: {agentcore_iam_role['Role']['Arn']}")

            # 設定を保存
            self.config["iam_role"] = {
                "role_name": agentcore_iam_role["Role"]["RoleName"],
                "role_arn": agentcore_iam_role["Role"]["Arn"],
            }
            self.save_config()

            return True

        except Exception as e:
            print(f"❌ IAM ロール処理エラー: {e}")
            import traceback

            traceback.print_exc()
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
            ecr_client = boto3.client("ecr", region_name=self.region)

            try:
                response = ecr_client.create_repository(
                    repositoryName=repository_name,
                    imageScanningConfiguration={"scanOnPush": True},
                )
                print(f"✓ ECR リポジトリを作成しました: {repository_name}")
                print(f"  リポジトリ URI: {response['repository']['repositoryUri']}")
            except ecr_client.exceptions.RepositoryAlreadyExistsException:
                print(f"✓ ECR リポジトリは既に存在します: {repository_name}")

            # 2. Docker ログイン
            print("\n2. ECR へのログイン...")
            login_cmd = f"aws ecr get-login-password --region {self.region} | docker login --username AWS --password-stdin {ecr_uri}"
            result = subprocess.run(
                login_cmd, shell=True, capture_output=True, text=True
            )

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
            build_cmd = (
                f"docker buildx build --platform linux/arm64 -t {image_uri} --push ."
            )
            result = subprocess.run(
                build_cmd, shell=True, capture_output=True, text=True, cwd=current_dir
            )

            if result.returncode == 0:
                print(f"✓ Docker イメージをビルドしてプッシュしました: {image_uri}")
            else:
                print(f"❌ Docker ビルドエラー: {result.stderr}")
                # ビルダーをクリーンアップ
                subprocess.run(
                    f"docker buildx rm {builder_name}", shell=True, capture_output=True
                )
                return False

            # ビルダーをクリーンアップ
            subprocess.run(
                f"docker buildx rm {builder_name}", shell=True, capture_output=True
            )

            # 設定を保存
            self.config["docker"] = {
                "repository_name": repository_name,
                "image_uri": image_uri,
                "ecr_uri": ecr_uri,
            }
            self.save_config()

            # 4. AgentCore Runtime へのデプロイ
            print("\n4. Bedrock AgentCore Runtime へのデプロイ...")

            # 必要な設定の確認
            if "iam_role" not in self.config:
                print(
                    "❌ エラー: IAM ロールが設定されていません。先にステップ 2 を実行してください。"
                )
                return False

            try:
                # AgentCore Control クライアントを作成
                agentcore_client = boto3.client(
                    "bedrock-agentcore-control", region_name=self.region
                )

                # エージェント名を生成（既存のものと重複しないように）
                import time

                agent_name = f"mcp_server_ac_{int(time.time())}"

                print(f"  エージェント名: {agent_name}")
                print(f"  イメージ URI: {image_uri}")
                print(f"  IAM ロール: {self.config['iam_role']['role_arn']}")

                # AgentCore Runtime を作成
                # 注: authorizerConfiguration を指定しない場合、デフォルトで SigV4 認証が使用されます
                # JWT Bearer Token 認証を使用する場合は、authorizerConfiguration パラメータを指定する必要があります
                response = agentcore_client.create_agent_runtime(
                    agentRuntimeName=agent_name,
                    agentRuntimeArtifact={
                        "containerConfiguration": {"containerUri": image_uri}
                    },
                    networkConfiguration={"networkMode": "PUBLIC"},
                    roleArn=self.config["iam_role"]["role_arn"],
                    protocolConfiguration={
                        "serverProtocol": "MCP"  # MCPプロトコルを明示的に指定
                    },
                    # authorizerConfiguration を指定しないため、デフォルトで SigV4 認証が使用されます
                )

                agent_arn = response["agentRuntimeArn"]
                status = response["status"]

                print("\n✓ AgentCore Runtime が正常に作成されました！")
                print(f"  エージェント ARN: {agent_arn}")
                print(f"  ステータス: {status}")

                # 設定を保存
                self.config["agent_runtime"] = {
                    "agent_name": agent_name,
                    "agent_arn": agent_arn,
                    "status": status,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.save_config()

                # Cognito 設定がある場合は表示
                if "cognito" in self.config:
                    print("\n  Cognito 設定:")
                    print(
                        f"    - Discovery URL: {self.config['cognito'].get('discovery_url', 'N/A')}"
                    )
                    print(
                        f"    - Client ID: {self.config['cognito'].get('client_id', 'N/A')}"
                    )

                print("\n✅ ステップ 4 が完了しました。")
                print("   エージェント ARN は自動的に保存されました。")
                print("   次のステップ 5 では、この ARN を使用して設定を完了します。")

                return True

            except Exception as e:
                print(f"❌ AgentCore Runtime デプロイエラー: {e}")
                print("\n詳細なエラー情報:")
                import traceback

                traceback.print_exc()
                return False

        except Exception as e:
            print(f"❌ Docker デプロイメントエラー: {e}")
            return False

    def step5_save_configuration(self, agent_arn=None):
        """ステップ 5: リモートアクセス用の設定保存"""
        print("\n=== ステップ 5: 設定の保存 ===")

        # agent_arnが指定されていない場合、保存された設定から取得
        if not agent_arn:
            if (
                "agent_runtime" in self.config
                and "agent_arn" in self.config["agent_runtime"]
            ):
                agent_arn = self.config["agent_runtime"]["agent_arn"]
                print(f"✓ 保存された設定から Agent ARN を取得しました: {agent_arn}")
            else:
                print("❌ エラー: エージェント ARN が見つかりません。")
                print("   先にステップ 4 を実行してエージェントをデプロイするか、")
                print("   --agent-arn オプションで手動指定してください。")
                print(
                    "   使用方法: python deploy.py --step5 --agent-arn <YOUR_AGENT_ARN>"
                )
                return False

        if "cognito" not in self.config:
            print(
                "❌ エラー: Cognito 設定が見つかりません。先にステップ 1 を実行してください。"
            )
            return False

        ssm_client = boto3.client("ssm", region_name=self.region)
        secrets_client = boto3.client("secretsmanager", region_name=self.region)

        try:
            # Cognito 認証情報を Secrets Manager に保存
            secret_name = "mcp_server/cognito/credentials"

            try:
                secrets_client.create_secret(
                    Name=secret_name,
                    Description="MCP Server 用の Cognito 認証情報",
                    SecretString=json.dumps(self.config["cognito"]),
                )
                print("✓ Cognito 認証情報を Secrets Manager に保存しました")
            except secrets_client.exceptions.ResourceExistsException:
                secrets_client.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(self.config["cognito"]),
                )
                print("✓ Cognito 認証情報を Secrets Manager で更新しました")

            # エージェント ARN を Parameter Store に保存
            param_name = "/mcp_server/runtime/agent_arn"
            ssm_client.put_parameter(
                Name=param_name,
                Value=agent_arn,
                Type="String",
                Description="MCP Server 用のエージェント ARN",
                Overwrite=True,
            )

            print("✓ エージェント ARN を Parameter Store に保存しました")
            print(f"  パラメータ名: {param_name}")
            print(f"  値: {agent_arn}")

            # 設定を保存
            self.config["agent_arn"] = agent_arn
            self.save_config()

            print("\n✅ ステップ 5 が完了しました。")
            print("   リモートアクセス用の設定がすべて保存されました。")

            return True

        except Exception as e:
            print(f"❌ 設定保存エラー: {e}")
            return False

    def run_all_steps(self, agent_arn=None):
        """全ステップを順番に実行"""
        print("=== 全ステップを実行します ===")

        # ステップ 1
        if not self.step1_setup_cognito():
            print("ステップ 1 で失敗しました。")
            return False

        # ステップ 2（自動更新対応）
        if not self.step2_create_iam_role():
            print("ステップ 2 で失敗しました。")
            return False

        # ステップ 3（情報表示のみ）
        self.step3_local_development()

        # ステップ 4（自動実行）
        if not self.step4_docker_deployment():
            print("ステップ 4 で失敗しました。")
            return False

        # ステップ 5（自動実行 - step4で作成されたagent_arnを使用）
        if not self.step5_save_configuration(agent_arn):
            print("ステップ 5 で失敗しました。")
            return False

        # 認証テストを実行
        from utils import run_auth_test

        run_auth_test(self.config, self.region)

        print("\n✅ 全ステップが完了しました！")
        print("   MCP Server が Amazon Bedrock AgentCore に正常にデプロイされました。")
        print("   IAM ロールは最新の bedrock-agentcore 権限で自動更新されました。")

        return True

    def check_agent_status(self):
        """デプロイされたエージェントのステータスを確認"""
        print("\n=== エージェントステータス確認 ===")

        # deployment_config.jsonから設定を確認
        if "agent_runtime" not in self.config:
            print("❌ エラー: エージェント情報が見つかりません。")
            print("   先にステップ 4 でエージェントをデプロイしてください。")
            return False

        agent_info = self.config["agent_runtime"]
        agent_arn = agent_info.get("agent_arn")
        agent_name = agent_info.get("agent_name")

        if not agent_arn:
            print("❌ エラー: エージェント ARN が見つかりません。")
            return False

        # ARN から Runtime ID を抽出
        # ARN形式: arn:aws:bedrock-agentcore:region:account:runtime/runtime-id
        try:
            agent_runtime_id = agent_arn.split("/")[-1]
        except Exception as e:
            print(f"❌ エラー: ARN からランタイム ID を抽出できません: {e}")
            return False

        print(f"エージェント名: {agent_name}")
        print(f"エージェント ARN: {agent_arn}")
        print(f"ランタイム ID: {agent_runtime_id}")
        print(f"作成日時: {agent_info.get('created_at', 'N/A')}")

        try:
            # 正しいクライアント名を使用（公式ドキュメントに基づく）
            agentcore_client = boto3.client(
                "bedrock-agentcore-control", region_name=self.region
            )

            print("\nエージェントステータスを取得中...")

            # 正しいパラメータでAPIを呼び出し
            response = agentcore_client.get_agent_runtime(
                agentRuntimeId=agent_runtime_id
            )

            # ステータス情報を表示
            status = response.get("status", "UNKNOWN")
            created_at = response.get("createdAt", "N/A")
            updated_at = response.get("lastUpdatedAt", "N/A")

            print("\n✓ エージェントステータス取得完了:")
            print(f"  ステータス: {status}")
            print(f"  作成日時: {created_at}")
            print(f"  更新日時: {updated_at}")

            # ステータスに応じたメッセージを表示
            if status == "READY":
                print("  🟢 エージェントは正常に動作しています")
            elif status == "CREATING":
                print("  🟡 エージェントは作成中です")
            elif status == "CREATE_FAILED":
                print("  🔴 エージェントの作成に失敗しました")
            elif status == "UPDATING":
                print("  🟡 エージェントは更新中です")
            elif status == "UPDATE_FAILED":
                print("  🔴 エージェントの更新に失敗しました")
            elif status == "DELETING":
                print("  🟡 エージェントは削除中です")
            else:
                print(f"  ⚪ 不明なステータス: {status}")

            # 追加情報があれば表示
            if "agentRuntimeName" in response:
                print(f"  エージェント名: {response['agentRuntimeName']}")
            if "description" in response:
                print(f"  説明: {response['description']}")
            if "agentRuntimeArtifact" in response:
                artifact = response["agentRuntimeArtifact"]
                if "containerConfiguration" in artifact:
                    container_uri = artifact["containerConfiguration"].get(
                        "containerUri", "N/A"
                    )
                    print(f"  コンテナ URI: {container_uri}")
            if "networkConfiguration" in response:
                network_mode = response["networkConfiguration"].get(
                    "networkMode", "N/A"
                )
                print(f"  ネットワークモード: {network_mode}")
            if "roleArn" in response:
                print(f"  IAM ロール: {response['roleArn']}")
            if "protocolConfiguration" in response:
                protocol = response["protocolConfiguration"].get(
                    "serverProtocol", "N/A"
                )
                print(f"  プロトコル: {protocol}")

            # 設定ファイルのステータスを更新
            self.config["agent_runtime"]["last_status_check"] = {
                "status": status,
                "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": str(created_at),
                "updated_at": str(updated_at),
            }
            self.save_config()

            return True

        except Exception as e:
            print(f"❌ エージェントステータス取得エラー: {e}")
            print("\n詳細なエラー情報:")
            import traceback

            traceback.print_exc()
            return False

    def put_role_policy(
        self, role_name=None, policy_name="bedrock-agentcore-policy", policy_file=None
    ):
        """指定したロールにポリシーを適用"""
        from pathlib import Path

        from utils import put_role_policy

        policy_document = None

        # ポリシーファイルが指定されている場合は読み込み
        if policy_file:
            policy_path = Path(policy_file)
            if not policy_path.exists():
                print(f"❌ エラー: ポリシーファイルが見つかりません: {policy_file}")
                return False

            try:
                with open(policy_path, "r") as f:
                    policy_document = json.loads(f.read())
                print(f"✓ ポリシーファイルを読み込み: {policy_file}")
            except (json.JSONDecodeError, Exception) as e:
                print(f"❌ エラー: ポリシーファイルの読み込みに失敗: {e}")
                return False

        # utils.py の関数を呼び出し
        return put_role_policy(
            role_name=role_name,
            policy_name=policy_name,
            policy_document=policy_document,
            boto_session=self.boto_session,
            region=self.region,
        )

    def get_role_policy(self, role_name=None, policy_name="bedrock-agentcore-policy"):
        """指定したロールのポリシーを取得"""
        from utils import get_role_policy

        # utils.py の関数を呼び出し
        result = get_role_policy(
            role_name=role_name,
            policy_name=policy_name,
            boto_session=self.boto_session,
            region=self.region,
        )

        return result is not None

    def show_current_role_info(self):
        """現在の実行ロールの詳細情報を表示"""
        from utils import show_current_role_info

        return show_current_role_info(self.boto_session, self.region)

    def show_status(self):
        """現在の設定状態を表示"""
        print("\n=== 現在の設定状態 ===")

        if "cognito" in self.config:
            print("\n✓ Cognito 設定:")
            print(
                f"  ユーザープール ID: {self.config['cognito'].get('pool_id', 'N/A')}"
            )
            print(f"  Client ID: {self.config['cognito'].get('client_id', 'N/A')}")
        else:
            print("\n❌ Cognito 設定: 未設定")

        if "iam_role" in self.config:
            print("\n✓ IAM ロール:")
            print(f"  ロール名: {self.config['iam_role'].get('role_name', 'N/A')}")
            print(f"  ロール ARN: {self.config['iam_role'].get('role_arn', 'N/A')}")
        else:
            print("\n❌ IAM ロール: 未作成")

        if "docker" in self.config:
            print("\n✓ Docker 設定:")
            print(
                f"  リポジトリ名: {self.config['docker'].get('repository_name', 'N/A')}"
            )
            print(f"  イメージ URI: {self.config['docker'].get('image_uri', 'N/A')}")
        else:
            print("\n❌ Docker 設定: 未設定")

        if "agent_runtime" in self.config:
            print("\n✓ エージェント Runtime:")
            agent_info = self.config["agent_runtime"]
            print(f"  エージェント名: {agent_info.get('agent_name', 'N/A')}")
            print(f"  エージェント ARN: {agent_info.get('agent_arn', 'N/A')}")
            print(f"  作成日時: {agent_info.get('created_at', 'N/A')}")

            # 最後のステータスチェック結果があれば表示
            if "last_status_check" in agent_info:
                status_info = agent_info["last_status_check"]
                print(f"  最新ステータス: {status_info.get('status', 'N/A')}")
                print(f"  最終確認日時: {status_info.get('checked_at', 'N/A')}")
        else:
            print("\n❌ エージェント Runtime: 未デプロイ")

        if "agent_arn" in self.config:
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
        description="MCP Server を Amazon Bedrock AgentCore にデプロイするための自動化スクリプト（ロール自動更新対応）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
uv run deploy.py --step1              # Cognito 設定
uv run deploy.py --step2              # IAM ロール作成/更新（自動処理）
uv run deploy.py --step3              # ローカル開発手順を表示
uv run deploy.py --step4              # Docker ビルドと ECR プッシュ（自動実行）
uv run deploy.py --step5 --agent-arn arn:aws:...  # 設定保存
uv run deploy.py --all                # 全ステップ実行
uv run deploy.py --status             # 現在の設定状態を表示
uv run deploy.py --update-token       # トークンを更新してSecrets Managerに保存
uv run deploy.py --test-auth          # 認証メソッドテストを実行
uv run deploy.py --put-role-policy    # 現在のプロファイルの実行ロールにポリシーを適用
uv run deploy.py --get-role-policy    # 現在のプロファイルの実行ロールのポリシーを取得
uv run deploy.py --put-role-policy --role-name <role-name> --policy-name <policy-name> --policy-file <file>
uv run deploy.py --get-role-policy --role-name <role-name> --policy-name <policy-name>
uv run deploy.py --show-current-role  # 現在の実行ロールの詳細情報を表示

注意: --policy-file を指定しない場合、デフォルトの Bedrock AgentCore ポリシーが使用されます。
""",
    )

    # ステップオプション
    parser.add_argument(
        "--step1",
        action="store_true",
        help="ステップ 1: Amazon Cognito ユーザープールの設定",
    )
    parser.add_argument(
        "--step2",
        action="store_true",
        help="ステップ 2: IAM 実行ロールの作成/更新（自動処理）",
    )
    parser.add_argument(
        "--step3", action="store_true", help="ステップ 3: ローカル開発手順を表示"
    )
    parser.add_argument(
        "--step4",
        action="store_true",
        help="ステップ 4: Docker イメージのビルドと ECR へのプッシュ（自動実行）",
    )
    parser.add_argument(
        "--step5", action="store_true", help="ステップ 5: リモートアクセス用の設定保存"
    )
    parser.add_argument(
        "--test-auth", action="store_true", help="認証メソッドテストを実行"
    )
    parser.add_argument(
        "--sigv4-list-tools",
        action="store_true",
        help="SigV4 認証を使用して AgentCore Runtime の MCP ツールリストを取得して表示",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["pretty", "json", "raw"],
        default="pretty",
        help="ツールリストの出力形式 (pretty: 整形表示, json: JSON形式, raw: 生データ)",
    )

    # その他のオプション
    parser.add_argument("--all", action="store_true", help="全ステップを順番に実行")
    parser.add_argument("--status", action="store_true", help="現在の設定状態を表示")
    parser.add_argument(
        "--check-status",
        action="store_true",
        help="デプロイされたエージェントのステータスを確認",
    )
    parser.add_argument(
        "--update-token", action="store_true", help="トークンのみを更新する"
    )
    parser.add_argument(
        "--agent-arn", type=str, help="エージェント ARN（ステップ 5 で必要）"
    )

    # IAM ポリシー管理オプション
    parser.add_argument(
        "--put-role-policy",
        action="store_true",
        help="現在のプロファイルの実行ロールにポリシーを適用",
    )
    parser.add_argument(
        "--get-role-policy",
        action="store_true",
        help="現在のプロファイルの実行ロールのポリシーを取得",
    )
    parser.add_argument(
        "--role-name",
        type=str,
        help="対象のロール名（指定しない場合は現在のプロファイルから自動取得）",
    )
    parser.add_argument(
        "--policy-name",
        type=str,
        default="bedrock-agentcore-policy",
        help="ポリシー名（デフォルト: bedrock-agentcore-policy）",
    )
    parser.add_argument(
        "--policy-file",
        type=str,
        default="bedrock-agentcore-policy.json",
        help="ポリシーファイルのパス（デフォルト: bedrock-agentcore-policy.json）",
    )
    parser.add_argument(
        "--show-current-role",
        action="store_true",
        help="現在の実行ロールの詳細情報を表示",
    )

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
    elif args.check_status:
        deployer.check_agent_status()
    elif args.all:
        deployer.run_all_steps(args.agent_arn)
    elif args.update_token:
        deployer.update_token()
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
    elif args.put_role_policy:
        deployer.put_role_policy(args.role_name, args.policy_name, args.policy_file)
    elif args.get_role_policy:
        deployer.get_role_policy(args.role_name, args.policy_name)
    elif args.show_current_role:
        deployer.show_current_role_info()
    elif args.test_auth:
        # 認証テストを実行（utils.pyの共通関数を使用）
        from utils import run_auth_test

        run_auth_test(deployer.config, deployer.region)
    elif args.sigv4_list_tools:
        # エージェント ARN を取得
        if (
            "agent_runtime" in deployer.config
            and "agent_arn" in deployer.config["agent_runtime"]
        ):
            agent_arn = deployer.config["agent_runtime"]["agent_arn"]
        elif "agent_arn" in deployer.config:
            agent_arn = deployer.config["agent_arn"]
        elif args.agent_arn:
            agent_arn = args.agent_arn
        else:
            print("❌ エラー: エージェント ARN が見つかりません。")
            print(
                "   --agent-arn オプションで指定するか、先にデプロイを実行してください。"
            )
            return

        # ツールリストを取得して表示
        from utils import sigv4_list_mcp_tools

        sigv4_list_mcp_tools(agent_arn, deployer.region, args.output_format)


if __name__ == "__main__":
    main()
