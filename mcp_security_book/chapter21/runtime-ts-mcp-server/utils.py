import json
import time

import boto3
from boto3.session import Session


def setup_cognito_user_pool():
    boto_session = Session()
    region = boto_session.region_name

    # Initialize Cognito client
    cognito_client = boto3.client("cognito-idp", region_name=region)

    try:
        # Create User Pool
        user_pool_response = cognito_client.create_user_pool(
            PoolName="MCPServerPool", Policies={"PasswordPolicy": {"MinimumLength": 8}}
        )
        pool_id = user_pool_response["UserPool"]["Id"]

        # Create App Client
        app_client_response = cognito_client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="MCPServerPoolClient",
            GenerateSecret=False,
            ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        )
        client_id = app_client_response["UserPoolClient"]["ClientId"]

        # Create User
        cognito_client.admin_create_user(
            UserPoolId=pool_id,
            Username="testuser",
            TemporaryPassword="Temp123!",
            MessageAction="SUPPRESS",
        )

        # Set Permanent Password
        cognito_client.admin_set_user_password(
            UserPoolId=pool_id,
            Username="testuser",
            Password="MyPassword123!",
            Permanent=True,
        )

        # Authenticate User and get Access Token
        auth_response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": "testuser", "PASSWORD": "MyPassword123!"},
        )
        bearer_token = auth_response["AuthenticationResult"]["AccessToken"]

        # Output the required values
        print(f"Pool id: {pool_id}")
        print(
            f"Discovery URL: https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
        )
        print(f"Client ID: {client_id}")
        print(f"Bearer Token: {bearer_token}")

        # Return values if needed for further processing
        return {
            "pool_id": pool_id,
            "client_id": client_id,
            "bearer_token": bearer_token,
            "discovery_url": f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration",
        }
    except Exception as e:
        print(f"Error: {e}")
        return None


def reauthenticate_user(client_id):
    boto_session = Session()
    region = boto_session.region_name

    # Initialize Cognito client
    cognito_client = boto3.client("cognito-idp", region_name=region)

    # Authenticate User and get Access Token
    auth_response = cognito_client.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": "testuser", "PASSWORD": "MyPassword123!"},
    )
    bearer_token = auth_response["AuthenticationResult"]["AccessToken"]
    return bearer_token


def create_agentcore_role(agent_name):
    iam_client = boto3.client("iam")
    agentcore_role_name = f"agentcore-{agent_name}-role"
    boto_session = Session()
    region = boto_session.region_name
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    # 修正版：bedrock-agentcore権限を追加
    role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockPermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeAgent",
                    "bedrock:GetAgent",
                    "bedrock:ListAgents",
                ],
                "Resource": "*",
            },
            {
                "Sid": "BedrockAgentCorePermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeAgent",
                    "bedrock-agentcore:GetAgent",
                    "bedrock-agentcore:ListAgents",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:*",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:*",
                ],
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                ],
                "Resource": [f"arn:aws:ecr:{region}:{account_id}:repository/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogGroups"],
                "Resource": [f"arn:aws:logs:{region}:{account_id}:log-group:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ],
            },
            {
                "Sid": "ECRTokenAccess",
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": ["*"],
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                },
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*",
                ],
            },
        ],
    }

    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": f"{account_id}"},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    },
                },
            }
        ],
    }

    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    role_policy_document = json.dumps(role_policy)

    # Create IAM Role for the Lambda function
    try:
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json,
        )
        # Pause to make sure role is created
        time.sleep(10)
    except iam_client.exceptions.EntityAlreadyExistsException:
        print("Role already exists -- deleting and creating it again")

        # インラインポリシーを削除
        policies = iam_client.list_role_policies(
            RoleName=agentcore_role_name, MaxItems=100
        )
        print("inline policies:", policies)
        for policy_name in policies["PolicyNames"]:
            print(f"deleting inline policy: {policy_name}")
            iam_client.delete_role_policy(
                RoleName=agentcore_role_name, PolicyName=policy_name
            )

        # マネージドポリシーをデタッチ
        attached_policies = iam_client.list_attached_role_policies(
            RoleName=agentcore_role_name
        )
        print("managed policies:", attached_policies)
        for policy in attached_policies.get("AttachedPolicies", []):
            policy_arn = policy["PolicyArn"]
            print(f"detaching managed policy: {policy_arn}")
            iam_client.detach_role_policy(
                RoleName=agentcore_role_name, PolicyArn=policy_arn
            )

        print(f"deleting {agentcore_role_name}")
        iam_client.delete_role(RoleName=agentcore_role_name)

        print(f"recreating {agentcore_role_name}")
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json,
        )

    # Attach the AWSLambdaBasicExecutionRole policy
    print(f"attaching role policy {agentcore_role_name}")
    try:
        iam_client.put_role_policy(
            PolicyDocument=role_policy_document,
            PolicyName="AgentCorePolicy",
            RoleName=agentcore_role_name,
        )
    except Exception as e:
        print(e)

    return agentcore_iam_role


def update_agentcore_role(agent_name):
    """
    IAM ロールを作成または更新する（自動処理）

    既存のロールがある場合は権限を更新し、
    ない場合は新規作成する。
    """
    iam_client = boto3.client("iam")
    agentcore_role_name = f"agentcore-{agent_name}-role"
    boto_session = Session()
    region = boto_session.region_name
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    print(f"IAM ロール '{agentcore_role_name}' を確認中...")

    # 修正版：bedrock-agentcore権限を含む完全なポリシー
    role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockPermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeAgent",
                    "bedrock:GetAgent",
                    "bedrock:ListAgents",
                ],
                "Resource": "*",
            },
            {
                "Sid": "BedrockAgentCorePermissions",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeAgent",
                    "bedrock-agentcore:GetAgent",
                    "bedrock-agentcore:ListAgents",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:*",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:*",
                ],
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                ],
                "Resource": [f"arn:aws:ecr:{region}:{account_id}:repository/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogGroups"],
                "Resource": [f"arn:aws:logs:{region}:{account_id}:log-group:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ],
            },
            {
                "Sid": "ECRTokenAccess",
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": ["*"],
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                },
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*",
                ],
            },
        ],
    }

    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": f"{account_id}"},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    },
                },
            }
        ],
    }

    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    role_policy_document = json.dumps(role_policy)

    try:
        # 既存のロールを確認
        try:
            existing_role = iam_client.get_role(RoleName=agentcore_role_name)
            print(f"✓ 既存のロール '{agentcore_role_name}' が見つかりました")
            print("  ロールの権限を最新版に更新中...")

            # 既存のインラインポリシーを削除
            policies = iam_client.list_role_policies(
                RoleName=agentcore_role_name, MaxItems=100
            )
            for policy_name in policies["PolicyNames"]:
                print(f"  既存のポリシー '{policy_name}' を削除中...")
                iam_client.delete_role_policy(
                    RoleName=agentcore_role_name, PolicyName=policy_name
                )

            # 既存のマネージドポリシーをデタッチ
            attached_policies = iam_client.list_attached_role_policies(
                RoleName=agentcore_role_name
            )
            for policy in attached_policies.get("AttachedPolicies", []):
                policy_arn = policy["PolicyArn"]
                print(f"  マネージドポリシー '{policy_arn}' をデタッチ中...")
                iam_client.detach_role_policy(
                    RoleName=agentcore_role_name, PolicyArn=policy_arn
                )

            # 信頼関係ポリシーを更新
            iam_client.update_assume_role_policy(
                RoleName=agentcore_role_name,
                PolicyDocument=assume_role_policy_document_json,
            )
            print("  信頼関係ポリシーを更新しました")

            # 新しいポリシーを適用
            iam_client.put_role_policy(
                PolicyDocument=role_policy_document,
                PolicyName="AgentCorePolicy",
                RoleName=agentcore_role_name,
            )
            print("  ✓ 新しい権限ポリシーを適用しました")
            print("    - bedrock-agentcore:* 権限を追加")
            print("    - 既存の権限も保持")

            agentcore_iam_role = existing_role

        except iam_client.exceptions.NoSuchEntityException:
            # ロールが存在しない場合は新規作成
            print(f"ロール '{agentcore_role_name}' が存在しないため、新規作成します")

            agentcore_iam_role = iam_client.create_role(
                RoleName=agentcore_role_name,
                AssumeRolePolicyDocument=assume_role_policy_document_json,
            )

            # 少し待機してからポリシーを適用
            time.sleep(5)

            # ポリシーを適用
            iam_client.put_role_policy(
                PolicyDocument=role_policy_document,
                PolicyName="AgentCorePolicy",
                RoleName=agentcore_role_name,
            )
            print("  ✓ 新しいロールを作成し、権限を設定しました")

        print(f"✅ IAM ロール処理完了: {agentcore_role_name}")
        print(f"  ロール ARN: {agentcore_iam_role['Role']['Arn']}")
        print("  含まれる権限:")
        print("    - bedrock:* (基本的なBedrock権限)")
        print("    - bedrock-agentcore:* (AgentCore権限) ← 新規追加")
        print("    - ECR, CloudWatch, X-Ray権限")

        return agentcore_iam_role

    except Exception as e:
        print(f"❌ IAM ロール処理エラー: {e}")
        import traceback

        traceback.print_exc()
        raise e


def test_agentcore_authentication(agent_arn, region="us-east-1"):
    """
    AgentCore Runtime の認証方法をテストする

    OAuth Bearer Token と SigV4 の両方をテストして、
    どちらが正しい認証方法かを判定する
    """
    import json
    import subprocess
    import urllib.parse

    print("\n=== AgentCore 認証テスト ===")
    print(f"Agent ARN: {agent_arn}")
    print(f"Region: {region}")

    # URLエンコード
    encoded_arn = urllib.parse.quote(agent_arn, safe="")
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    print(f"URL: {url}")

    # テストペイロード
    test_payload = {
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"sampling": {}, "roots": {"listChanged": True}},
            "clientInfo": {"name": "mcp", "version": "0.1.0"},
        },
        "jsonrpc": "2.0",
        "id": 0,
    }

    # 1. OAuth Bearer Token テスト
    print("\n🔐 テスト 1: OAuth Bearer Token 認証")
    try:
        # Bearer tokenを取得
        secrets_client = boto3.client("secretsmanager", region_name=region)

        # Cognito認証情報を取得
        secret_response = secrets_client.get_secret_value(
            SecretId="mcp_server/cognito/credentials"
        )
        secret_data = json.loads(secret_response["SecretString"])
        bearer_token = secret_data["bearer_token"]

        # curlコマンドを構築
        curl_cmd = [
            "curl",
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: application/json, text/event-stream",
            "-H",
            f"Authorization: Bearer {bearer_token}",
            "-d",
            json.dumps(test_payload),
            "-s",
            "-w",
            "%{http_code}",
            "-o",
            "/tmp/oauth_response.json",
        ]

        # curlを実行
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        http_code = result.stdout.strip()

        # レスポンスを読み取り
        try:
            with open("/tmp/oauth_response.json", "r") as f:
                response_body = f.read()
        except Exception:
            response_body = ""

        print(f"  HTTP Status: {http_code}")
        if response_body:
            try:
                response_json = json.loads(response_body)
                if "message" in response_json:
                    print(f"  Message: {response_json['message']}")
            except Exception:
                print(f"  Response: {response_body[:200]}...")

        oauth_success = http_code == "200"
        print(f"  結果: {'✅ 成功' if oauth_success else '❌ 失敗'}")

    except Exception as e:
        print(f"  ❌ OAuth テストエラー: {e}")
        oauth_success = False

    # 2. SigV4 認証テスト
    print("\n🔐 テスト 2: SigV4 認証")
    try:
        # AWS CLIを使用してSigV4署名付きリクエストを送信
        # テストペイロード
        test_payload = {"method": "tools/list", "params": {}, "jsonrpc": "2.0", "id": 1}
        payload_str = json.dumps(test_payload)
        import base64

        payload_base64 = base64.b64encode(payload_str.encode()).decode()

        aws_cmd = [
            "aws",
            "bedrock-agentcore",
            "invoke-agent-runtime",
            "--agent-runtime-arn",
            agent_arn,
            "--content-type",
            "application/json",
            "--accept",
            "application/json, text/event-stream",
            "--payload",
            payload_base64,
            "--region",
            region,
            "--output",
            "json",
            "/tmp/sigv4_response.json",
        ]
        print(f"実行コマンド: {aws_cmd}")

        result = subprocess.run(aws_cmd, capture_output=True, text=True, timeout=30)

        print(f"  AWS CLI Exit Code: {result.returncode}")
        if result.stdout:
            print(f"  Output: {result.stdout[:200]}...")
        if result.stderr:
            print(f"  Error: {result.stderr[:200]}...")

        sigv4_success = result.returncode == 0
        print(f"  結果: {'✅ 成功' if sigv4_success else '❌ 失敗'}")

    except Exception as e:
        print(f"  ❌ SigV4 テストエラー: {e}")
        sigv4_success = False

    # 3. 直接curlでSigV4テスト（awscurlを使用）
    print("\n🔐 テスト 3: 直接 SigV4 curl")
    try:
        # awscurlがインストールされている場合
        awscurl_cmd = [
            "awscurl",
            "--service",
            "bedrock-agentcore",
            "--region",
            region,
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(test_payload),
            url,
        ]

        result = subprocess.run(awscurl_cmd, capture_output=True, text=True, timeout=30)

        print(f"  Exit Code: {result.returncode}")
        if result.stdout:
            print(f"  Output: {result.stdout[:200]}...")
        if result.stderr:
            print(f"  Error: {result.stderr[:200]}...")

        awscurl_success = result.returncode == 0
        print(f"  結果: {'✅ 成功' if awscurl_success else '❌ 失敗'}")

    except FileNotFoundError:
        print("  ⚠️  awscurl がインストールされていません")
        awscurl_success = False
    except Exception as e:
        print(f"  ❌ awscurl テストエラー: {e}")
        awscurl_success = False

    # 結果の判定
    print("\n📊 認証テスト結果:")
    print(f"  OAuth Bearer Token: {'✅ 動作' if oauth_success else '❌ 失敗'}")
    print(f"  SigV4 (AWS CLI):    {'✅ 動作' if sigv4_success else '❌ 失敗'}")
    print(f"  SigV4 (awscurl):    {'✅ 動作' if awscurl_success else '❌ 失敗'}")

    if oauth_success:
        recommended_auth = "OAuth Bearer Token"
        print(f"\n💡 推奨認証方法: {recommended_auth}")
        print("   uv run simple_protocol_debug_client.py を使用してください")
    elif sigv4_success or awscurl_success:
        recommended_auth = "SigV4"
        print(f"\n💡 推奨認証方法: {recommended_auth}")
    else:
        recommended_auth = "不明"
        print("\n❌ どの認証方法も動作しませんでした")
        print("   AgentCore Runtime の設定を確認してください")

    return {
        "oauth_success": oauth_success,
        "sigv4_success": sigv4_success,
        "awscurl_success": awscurl_success,
        "recommended_auth": recommended_auth,
    }


def get_detailed_curl_command(agent_arn, region="us-east-1", auth_method="oauth"):
    """
    詳細なcurlコマンドを生成する
    """
    import json
    import urllib.parse

    # URLエンコード
    encoded_arn = urllib.parse.quote(agent_arn, safe="")
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    # テストペイロード
    test_payload = {
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"sampling": {}, "roots": {"listChanged": True}},
            "clientInfo": {"name": "mcp", "version": "0.1.0"},
        },
        "jsonrpc": "2.0",
        "id": 0,
    }

    if auth_method.lower() == "oauth":
        # OAuth Bearer Token版
        curl_cmd = f"""curl -X POST \\
  "{url}" \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -H "Authorization: Bearer $(aws secretsmanager get-secret-value --secret-id 'mcp_server/cognito/credentials' --region {region} --query 'SecretString' --output text | jq -r '.bearer_token')" \\
  -d '{json.dumps(test_payload)}' \\
  -v"""
    else:
        # SigV4版（awscurl使用）
        curl_cmd = f'''awscurl --service bedrock-agentcore \\
  --region {region} \\
  -X POST \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -d '{json.dumps(test_payload)}' \\
  "{url}"'''

    return curl_cmd


def install_awscurl():
    """
    awscurlをインストールする
    """
    import subprocess

    print("🔧 awscurl をインストール中...")
    try:
        # pipでawscurlをインストール
        result = subprocess.run(
            ["pip", "install", "awscurl"], capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0:
            print("✅ awscurl のインストールが完了しました")
            return True
        else:
            print(f"❌ awscurl のインストールに失敗しました: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ awscurl のインストールエラー: {e}")
        return False


# =============================================================================
# IAM ロールポリシー管理機能
# =============================================================================

# Bedrock AgentCore ポリシーのデフォルト定義
DEFAULT_BEDROCK_AGENTCORE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockAgentCoreFullAccess",
            "Effect": "Allow",
            "Action": ["bedrock-agentcore:*"],
            "Resource": "*",
        },
        {
            "Sid": "BedrockFullAccess",
            "Effect": "Allow",
            "Action": ["bedrock:*"],
            "Resource": "*",
        },
    ],
}


def get_current_role_name(boto_session=None):
    """
    現在のプロファイルの実行ロール名を取得

    Args:
        boto_session: boto3.Session オブジェクト (オプション)

    Returns:
        str: ロール名、または None
    """
    if not boto_session:
        boto_session = Session()

    try:
        # STSで現在のアイデンティティを取得
        sts_client = boto_session.client("sts")
        identity = sts_client.get_caller_identity()
        arn = identity.get("Arn", "")

        # EC2 インスタンスプロファイルの場合
        if ":assumed-role/" in arn:
            # arn:aws:sts::account:assumed-role/role-name/instance-id から role-name を抽出
            role_name = arn.split("/")[-2]
            return role_name
        elif ":role/" in arn:
            # arn:aws:iam::account:role/role-name から role-name を抽出
            role_name = arn.split("/")[-1]
            return role_name
        else:
            print(f"⚠️  警告: ロールベースのアイデンティティではありません: {arn}")
            return None

    except Exception as e:
        print(f"❌ エラー: 現在のロール名を取得できません: {e}")
        return None


def put_role_policy(
    role_name=None,
    policy_name="bedrock-agentcore-policy",
    policy_document=None,
    boto_session=None,
    region=None,
):
    """
    指定したロールにポリシーを適用

    Args:
        role_name (str): ロール名 (指定しない場合は現在のプロファイルから自動取得)
        policy_name (str): ポリシー名
        policy_document (dict): ポリシードキュメント (指定しない場合はデフォルトのBedrock AgentCoreポリシー)
        boto_session: boto3.Session オブジェクト (オプション)
        region (str): AWS リージョン

    Returns:
        bool: 成功した場合 True
    """
    if not boto_session:
        boto_session = Session()

    if not region:
        region = boto_session.region_name or "us-east-1"

    print("\n=== IAM ロールポリシーの適用 ===")

    # ロール名が指定されていない場合は現在のプロファイルから取得
    if not role_name:
        role_name = get_current_role_name(boto_session)
        if not role_name:
            print(
                "❌ エラー: ロール名を取得できません。role_name パラメータで手動指定してください。"
            )
            return False
        print(f"✓ 現在のプロファイルのロール名を取得: {role_name}")

    # ポリシードキュメントが指定されていない場合はデフォルトを使用
    if not policy_document:
        policy_document = DEFAULT_BEDROCK_AGENTCORE_POLICY
        print("✓ デフォルトの Bedrock AgentCore ポリシーを使用")

    try:
        # IAM クライアントを作成
        iam_client = boto_session.client("iam")

        # ポリシーを適用
        print("ポリシーを適用中...")
        print(f"  ロール名: {role_name}")
        print(f"  ポリシー名: {policy_name}")
        print(f"  リージョン: {region}")

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(policy_document),
        )

        print("✓ ポリシーの適用が完了しました")
        print(
            f"  コマンド相当: aws iam put-role-policy --role-name {role_name} --policy-name {policy_name} --policy-document '<json>' --region {region}"
        )

        # 適用されたポリシーの概要を表示
        statements = policy_document.get("Statement", [])
        print("\n適用されたポリシーの概要:")
        for i, stmt in enumerate(statements):
            sid = stmt.get("Sid", f"Statement{i+1}")
            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            print(
                f"  - {sid}: {', '.join(actions[:3])}{'...' if len(actions) > 3 else ''}"
            )

        return True

    except Exception as e:
        print(f"❌ エラー: ポリシーの適用に失敗しました: {e}")
        import traceback

        traceback.print_exc()
        return False


def get_role_policy(
    role_name=None,
    policy_name="bedrock-agentcore-policy",
    boto_session=None,
    region=None,
):
    """
    指定したロールのポリシーを取得

    Args:
        role_name (str): ロール名 (指定しない場合は現在のプロファイルから自動取得)
        policy_name (str): ポリシー名
        boto_session: boto3.Session オブジェクト (オプション)
        region (str): AWS リージョン

    Returns:
        dict: ポリシードキュメント、または None
    """
    if not boto_session:
        boto_session = Session()

    if not region:
        region = boto_session.region_name or "us-east-1"

    print("\n=== IAM ロールポリシーの取得 ===")

    # ロール名が指定されていない場合は現在のプロファイルから取得
    if not role_name:
        role_name = get_current_role_name(boto_session)
        if not role_name:
            print(
                "❌ エラー: ロール名を取得できません。role_name パラメータで手動指定してください。"
            )
            return None
        print(f"✓ 現在のプロファイルのロール名を取得: {role_name}")

    try:
        # IAM クライアントを作成
        iam_client = boto_session.client("iam")

        print("ポリシーを取得中...")
        print(f"  ロール名: {role_name}")
        print(f"  ポリシー名: {policy_name}")
        print(f"  リージョン: {region}")

        response = iam_client.get_role_policy(
            RoleName=role_name, PolicyName=policy_name
        )

        policy_document = response.get("PolicyDocument", {})

        print("✓ ポリシーの取得が完了しました")
        print(
            f"  コマンド相当: aws iam get-role-policy --role-name {role_name} --policy-name {policy_name} --region {region}"
        )

        print("\n=== ポリシー内容 ===")
        print(json.dumps(policy_document, indent=2, ensure_ascii=False))

        return policy_document

    except iam_client.exceptions.NoSuchEntityException:
        print("❌ エラー: 指定したポリシーが見つかりません")
        print(f"  ロール名: {role_name}")
        print(f"  ポリシー名: {policy_name}")

        # ロールにアタッチされているポリシー一覧を表示
        try:
            policies_response = iam_client.list_role_policies(RoleName=role_name)
            policy_names = policies_response.get("PolicyNames", [])
            if policy_names:
                print(f"\nロール {role_name} にアタッチされているインラインポリシー:")
                for name in policy_names:
                    print(f"  - {name}")
            else:
                print(
                    f"\nロール {role_name} にインラインポリシーはアタッチされていません"
                )
        except Exception as list_error:
            print(f"ポリシー一覧の取得に失敗: {list_error}")

        return None
    except Exception as e:
        print(f"❌ エラー: ポリシーの取得に失敗しました: {e}")
        import traceback

        traceback.print_exc()
        return None


def run_auth_test(config, region="us-east-1"):
    """
    認証テストを実行する共通関数

    Args:
        config (dict): 設定情報（agent_arnを含む）
        region (str): AWS リージョン

    Returns:
        dict: テスト結果
    """
    print("\n=== 認証テスト実行 ===")

    # Agent ARNを取得
    if "agent_runtime" in config and "agent_arn" in config["agent_runtime"]:
        agent_arn = config["agent_runtime"]["agent_arn"]
    elif "agent_arn" in config:
        agent_arn = config["agent_arn"]
    else:
        print("❌ エラー: エージェント ARN が見つかりません。")
        return False

    print(f"Agent ARN: {agent_arn}")
    print(f"Region: {region}")

    # awscurlがない場合はインストール
    try:
        import subprocess

        subprocess.run(["awscurl", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("⚠️  awscurl が見つかりません。SigV4テストのためにインストールします。")
        install_awscurl()

    # 認証テストを実行
    test_result = test_agentcore_authentication(agent_arn, region)

    # 詳細なcurlコマンドを表示
    print("\n📋 詳細なcurlコマンド:")
    oauth_cmd = get_detailed_curl_command(agent_arn, region, "oauth")
    sigv4_cmd = get_detailed_curl_command(agent_arn, region, "sigv4")

    print("\n🔐 OAuth Bearer Token版:")
    print(oauth_cmd)
    print("\n🔐 SigV4版:")
    print(sigv4_cmd)

    # 推奨クライアントを表示
    print("\n🚀 推奨クライアント:")
    if test_result["oauth_success"]:
        print("  uv run simple_protocol_debug_client.py --region us-east-1")
    if test_result["sigv4_success"]:
        print("  uv run client.py")

    return test_result


def sigv4_list_mcp_tools(agent_arn, region="us-east-1", output_format="pretty"):
    """
    SigV4 認証を使用して AgentCore Runtime の MCP ツールリストを取得して表示する

    Args:
        agent_arn (str): エージェント ARN
        region (str): AWS リージョン
        output_format (str): 出力形式 ('pretty', 'json', 'raw')

    Returns:
        dict: ツールリスト情報
    """
    import base64
    import json
    import subprocess

    print("\n=== MCP ツールリスト取得 (SigV4認証) ===")
    print(f"Agent ARN: {agent_arn}")
    print(f"Region: {region}")

    # テストペイロード
    test_payload = {"method": "tools/list", "params": {}, "jsonrpc": "2.0", "id": 1}
    payload_str = json.dumps(test_payload)
    payload_base64 = base64.b64encode(payload_str.encode()).decode()

    # 一時ファイルのパスを指定
    output_file = "/tmp/sigv4_tools_response.json"

    # AWS CLIコマンドを構築
    aws_cmd = [
        "aws",
        "bedrock-agentcore",
        "invoke-agent-runtime",
        "--agent-runtime-arn",
        agent_arn,
        "--content-type",
        "application/json",
        "--accept",
        "application/json, text/event-stream",
        "--payload",
        payload_base64,
        "--region",
        region,
        "--output",
        "json",
        output_file,  # 出力ファイルを指定
    ]

    # コマンドを実行
    result = subprocess.run(aws_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ ツールリスト取得エラー: {result.stderr}")
        return None

    # 出力ファイルからレスポンスを読み取る
    try:
        with open(output_file, "r") as f:
            response = json.load(f)

        # レスポンスボディを取得
        if "body" in response:
            body_str = response["body"]
            body = json.loads(body_str)
        else:
            body = response

        # ツールリストを抽出
        if "result" in body and "tools" in body["result"]:
            tools = body["result"]["tools"]

            # 出力形式に応じて表示
            if output_format == "raw":
                print(json.dumps(body))
            elif output_format == "json":
                print(json.dumps(tools, indent=2, ensure_ascii=False))
            else:  # pretty
                print(f"\n✅ 利用可能な MCP ツール ({len(tools)}件):")

                for i, tool in enumerate(tools):
                    name = tool.get("name", "N/A")
                    title = tool.get("title", "N/A")
                    desc = tool.get("description", "N/A")

                    print(f"\n🔧 ツール {i+1}: {name}")
                    print(f"  タイトル: {title}")
                    print(f"  説明: {desc}")

                    # 入力スキーマがあれば表示
                    if "inputSchema" in tool:
                        schema = tool["inputSchema"]
                        print("  入力パラメータ:")

                        if "properties" in schema:
                            for param_name, param_info in schema["properties"].items():
                                param_type = param_info.get("type", "any")
                                param_desc = param_info.get("description", "")
                                required = (
                                    "必須"
                                    if param_name in schema.get("required", [])
                                    else "任意"
                                )

                                print(
                                    f"    - {param_name} ({param_type}, {required}): {param_desc}"
                                )

            return tools
        else:
            print("❌ ツールリストが見つかりません")
            print(f"レスポンス: {body}")
            return None

    except json.JSONDecodeError:
        print(f"❌ JSON 解析エラー: {result.stdout}")
        return None
    except Exception as e:
        print(f"❌ ツールリスト処理エラー: {e}")
        import traceback

        traceback.print_exc()
        return None


def show_current_role_info(boto_session=None, region=None):
    """
    現在の実行ロールの詳細情報を表示

    Args:
        boto_session: boto3.Session オブジェクト (オプション)
        region (str): AWS リージョン

    Returns:
        bool: 成功した場合 True
    """
    if not boto_session:
        boto_session = Session()

    if not region:
        region = boto_session.region_name or "us-east-1"

    print("\n=== 現在の実行ロール情報 ===")

    try:
        # STSで現在のアイデンティティを取得
        sts_client = boto_session.client("sts")
        identity = sts_client.get_caller_identity()

        print("✓ 現在のアイデンティティ:")
        print(f"  アカウント ID: {identity.get('Account', 'N/A')}")
        print(f"  ユーザー ID: {identity.get('UserId', 'N/A')}")
        print(f"  ARN: {identity.get('Arn', 'N/A')}")
        print(f"  リージョン: {region}")

        arn = identity.get("Arn", "")
        role_name = None

        # ロール名を抽出
        if ":assumed-role/" in arn:
            # arn:aws:sts::account:assumed-role/role-name/instance-id から role-name を抽出
            role_name = arn.split("/")[-2]
            print(f"\n✓ 抽出したロール名: {role_name}")
            print("  タイプ: Assumed Role (EC2 インスタンスプロファイルなど)")
        elif ":role/" in arn:
            # arn:aws:iam::account:role/role-name から role-name を抽出
            role_name = arn.split("/")[-1]
            print(f"\n✓ 抽出したロール名: {role_name}")
            print("  タイプ: IAM Role")
        else:
            print("\n⚠️  警告: ロールベースのアイデンティティではありません")
            print("  ユーザーベースのアイデンティティの可能性があります")
            return False

        if not role_name:
            print("❌ エラー: ロール名を抽出できませんでした")
            return False

        # IAM クライアントでロールの詳細情報を取得
        iam_client = boto_session.client("iam")

        print("\nロールの詳細情報を取得中...")

        try:
            # ロールの基本情報を取得
            role_response = iam_client.get_role(RoleName=role_name)
            role_info = role_response["Role"]

            print("\n=== ロールの基本情報 ===")
            print(f"  ロール名: {role_info.get('RoleName', 'N/A')}")
            print(f"  ロール ARN: {role_info.get('Arn', 'N/A')}")
            print(f"  作成日: {role_info.get('CreateDate', 'N/A')}")
            print(f"  パス: {role_info.get('Path', 'N/A')}")
            print(
                f"  最大セッション時間: {role_info.get('MaxSessionDuration', 'N/A')} 秒"
            )

            if "Description" in role_info:
                print(f"  説明: {role_info['Description']}")

            # 信頼ポリシーを表示
            assume_role_policy = role_info.get("AssumeRolePolicyDocument", {})
            if assume_role_policy:
                print("\n=== 信頼ポリシー ===")
                print(json.dumps(assume_role_policy, indent=2, ensure_ascii=False))

        except iam_client.exceptions.NoSuchEntityException:
            print(f"❌ エラー: ロール '{role_name}' が見つかりません")
            return False

        # アタッチされたマネージドポリシーを取得
        try:
            attached_policies_response = iam_client.list_attached_role_policies(
                RoleName=role_name
            )
            attached_policies = attached_policies_response.get("AttachedPolicies", [])

            if attached_policies:
                print(
                    f"\n=== アタッチされたマネージドポリシー ({len(attached_policies)}件) ==="
                )
                for policy in attached_policies:
                    print(f"  - {policy.get('PolicyName', 'N/A')}")
                    print(f"    ARN: {policy.get('PolicyArn', 'N/A')}")
            else:
                print("\nアタッチされたマネージドポリシーはありません")

        except Exception as e:
            print(f"マネージドポリシーの取得に失敗: {e}")

        # インラインポリシーを取得
        try:
            inline_policies_response = iam_client.list_role_policies(RoleName=role_name)
            inline_policy_names = inline_policies_response.get("PolicyNames", [])

            if inline_policy_names:
                print(f"\n=== インラインポリシー ({len(inline_policy_names)}件) ===")
                for policy_name in inline_policy_names:
                    print(f"  - {policy_name}")

                    # 各インラインポリシーの詳細を取得（オプション）
                    try:
                        policy_response = iam_client.get_role_policy(
                            RoleName=role_name, PolicyName=policy_name
                        )
                        policy_document = policy_response.get("PolicyDocument", {})

                        # ポリシーのサイズをチェックして、小さい場合のみ表示
                        policy_str = json.dumps(policy_document)
                        if len(policy_str) < 1000:  # 1KB未満の場合のみ表示
                            print("    ポリシー内容:")
                            print(
                                json.dumps(
                                    policy_document, indent=6, ensure_ascii=False
                                )
                            )
                        else:
                            print(
                                f"    ポリシーサイズ: {len(policy_str)} 文字 (大きいため略)"
                            )

                    except Exception as policy_error:
                        print(f"    ポリシー詳細の取得に失敗: {policy_error}")
            else:
                print("\nインラインポリシーはありません")

        except Exception as e:
            print(f"インラインポリシーの取得に失敗: {e}")

        # タグ情報を取得
        try:
            tags_response = iam_client.list_role_tags(RoleName=role_name)
            tags = tags_response.get("Tags", [])

            if tags:
                print(f"\n=== タグ ({len(tags)}件) ===")
                for tag in tags:
                    print(f"  {tag.get('Key', 'N/A')}: {tag.get('Value', 'N/A')}")
            else:
                print("\nタグは設定されていません")

        except Exception as e:
            print(f"タグ情報の取得に失敗: {e}")

        # コマンド例を表示
        print("\n=== 関連コマンド例 ===")
        print("# utils.py の関数を使用")
        print("from utils import put_role_policy, get_role_policy")
        print(f"put_role_policy('{role_name}')")
        print(f"get_role_policy('{role_name}')")
        print("\n# deploy.py で使用")
        print(f"uv run deploy.py --put-role-policy --role-name {role_name}")
        print(f"uv run deploy.py --get-role-policy --role-name {role_name}")
        print("\n# AWS CLI 相当コマンド")
        print(f"aws iam get-role --role-name {role_name} --region {region}")
        print(
            f"aws iam list-attached-role-policies --role-name {role_name} --region {region}"
        )
        print(f"aws iam list-role-policies --role-name {role_name} --region {region}")

        return True

    except Exception as e:
        print(f"❌ エラー: ロール情報の取得に失敗しました: {e}")
        import traceback

        traceback.print_exc()
        return False
