import boto3
import json
import time
from boto3.session import Session

def setup_cognito_user_pool():
    boto_session = Session()
    region = boto_session.region_name
    
    # Initialize Cognito client
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    try:
        # Create User Pool
        user_pool_response = cognito_client.create_user_pool(
            PoolName='MCPServerPool',
            Policies={'PasswordPolicy': {'MinimumLength': 8}}
        )
        pool_id = user_pool_response['UserPool']['Id']
        
        # Create App Client
        app_client_response = cognito_client.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName='MCPServerPoolClient',
            GenerateSecret=False,
            ExplicitAuthFlows=[
                'ALLOW_USER_PASSWORD_AUTH',
                'ALLOW_REFRESH_TOKEN_AUTH'
            ]
        )
        client_id = app_client_response['UserPoolClient']['ClientId']
        
        # Create User
        cognito_client.admin_create_user(
            UserPoolId=pool_id,
            Username='testuser',
            TemporaryPassword='Temp123!',
            MessageAction='SUPPRESS'
        )
        
        # Set Permanent Password
        cognito_client.admin_set_user_password(
            UserPoolId=pool_id,
            Username='testuser',
            Password='MyPassword123!',
            Permanent=True
        )
        
        # Authenticate User and get Access Token
        auth_response = cognito_client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': 'testuser',
                'PASSWORD': 'MyPassword123!'
            }
        )
        bearer_token = auth_response['AuthenticationResult']['AccessToken']
        
        # Output the required values
        print(f"Pool id: {pool_id}")
        print(f"Discovery URL: https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration")
        print(f"Client ID: {client_id}")
        print(f"Bearer Token: {bearer_token}")
        
        # Return values if needed for further processing
        return {
            'pool_id': pool_id,
            'client_id': client_id,
            'bearer_token': bearer_token,
            'discovery_url': f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

def reauthenticate_user(client_id):
    boto_session = Session()
    region = boto_session.region_name
    
    # Initialize Cognito client
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    # Authenticate User and get Access Token
    auth_response = cognito_client.initiate_auth(
        ClientId=client_id,
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': 'testuser',
            'PASSWORD': 'MyPassword123!'
        }
    )
    bearer_token = auth_response['AuthenticationResult']['AccessToken']
    return bearer_token

def create_agentcore_role(agent_name):
    iam_client = boto3.client('iam')
    agentcore_role_name = f'agentcore-{agent_name}-role'
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
                    "bedrock:ListAgents"
                ],
                "Resource": "*"
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
                    "bedrock-agentcore:*"
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                ]
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer"
                ],
                "Resource": [
                    f"arn:aws:ecr:{region}:{account_id}:repository/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogGroups"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ]
            },
            {
                "Sid": "ECRTokenAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets"
                ],
                "Resource": [ "*" ]
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore"
                    }
                }
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*"
                ]
            }
        ]
    }
    
    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": f"{account_id}"
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    }
                }
            }
        ]
    }
    
    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    role_policy_document = json.dumps(role_policy)
    
    # Create IAM Role for the Lambda function
    try:
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json
        )
        # Pause to make sure role is created
        time.sleep(10)
    except iam_client.exceptions.EntityAlreadyExistsException:
        print("Role already exists -- deleting and creating it again")
        
        # インラインポリシーを削除
        policies = iam_client.list_role_policies(
            RoleName=agentcore_role_name,
            MaxItems=100
        )
        print("inline policies:", policies)
        for policy_name in policies['PolicyNames']:
            print(f"deleting inline policy: {policy_name}")
            iam_client.delete_role_policy(
                RoleName=agentcore_role_name,
                PolicyName=policy_name
            )
        
        # マネージドポリシーをデタッチ
        attached_policies = iam_client.list_attached_role_policies(RoleName=agentcore_role_name)
        print("managed policies:", attached_policies)
        for policy in attached_policies.get('AttachedPolicies', []):
            policy_arn = policy['PolicyArn']
            print(f"detaching managed policy: {policy_arn}")
            iam_client.detach_role_policy(
                RoleName=agentcore_role_name,
                PolicyArn=policy_arn
            )
        
        print(f"deleting {agentcore_role_name}")
        iam_client.delete_role(RoleName=agentcore_role_name)
        
        print(f"recreating {agentcore_role_name}")
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json
        )
    
    # Attach the AWSLambdaBasicExecutionRole policy
    print(f"attaching role policy {agentcore_role_name}")
    try:
        iam_client.put_role_policy(
            PolicyDocument=role_policy_document,
            PolicyName="AgentCorePolicy",
            RoleName=agentcore_role_name
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
    iam_client = boto3.client('iam')
    agentcore_role_name = f'agentcore-{agent_name}-role'
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
                    "bedrock:ListAgents"
                ],
                "Resource": "*"
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
                    "bedrock-agentcore:*"
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                ]
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer"
                ],
                "Resource": [
                    f"arn:aws:ecr:{region}:{account_id}:repository/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogGroups"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ]
            },
            {
                "Sid": "ECRTokenAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets"
                ],
                "Resource": [ "*" ]
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore"
                    }
                }
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*"
                ]
            }
        ]
    }
    
    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": f"{account_id}"
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    }
                }
            }
        ]
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
            policies = iam_client.list_role_policies(RoleName=agentcore_role_name, MaxItems=100)
            for policy_name in policies['PolicyNames']:
                print(f"  既存のポリシー '{policy_name}' を削除中...")
                iam_client.delete_role_policy(
                    RoleName=agentcore_role_name,
                    PolicyName=policy_name
                )
            
            # 既存のマネージドポリシーをデタッチ
            attached_policies = iam_client.list_attached_role_policies(RoleName=agentcore_role_name)
            for policy in attached_policies.get('AttachedPolicies', []):
                policy_arn = policy['PolicyArn']
                print(f"  マネージドポリシー '{policy_arn}' をデタッチ中...")
                iam_client.detach_role_policy(
                    RoleName=agentcore_role_name,
                    PolicyArn=policy_arn
                )
            
            # 信頼関係ポリシーを更新
            iam_client.update_assume_role_policy(
                RoleName=agentcore_role_name,
                PolicyDocument=assume_role_policy_document_json
            )
            print("  信頼関係ポリシーを更新しました")
            
            # 新しいポリシーを適用
            iam_client.put_role_policy(
                PolicyDocument=role_policy_document,
                PolicyName="AgentCorePolicy",
                RoleName=agentcore_role_name
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
                AssumeRolePolicyDocument=assume_role_policy_document_json
            )
            
            # 少し待機してからポリシーを適用
            time.sleep(5)
            
            # ポリシーを適用
            iam_client.put_role_policy(
                PolicyDocument=role_policy_document,
                PolicyName="AgentCorePolicy",
                RoleName=agentcore_role_name
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

def test_agentcore_authentication(agent_arn, region='us-east-1'):
    """
    AgentCore Runtime の認証方法をテストする
    
    OAuth Bearer Token と SigV4 の両方をテストして、
    どちらが正しい認証方法かを判定する
    """
    import subprocess
    import json
    import urllib.parse
    
    print(f"\n=== AgentCore 認証テスト ===")
    print(f"Agent ARN: {agent_arn}")
    print(f"Region: {region}")
    
    # URLエンコード
    encoded_arn = urllib.parse.quote(agent_arn, safe='')
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    print(f"URL: {url}")
    
    # テストペイロード
    test_payload = {
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "sampling": {},
                "roots": {"listChanged": True}
            },
            "clientInfo": {"name": "mcp", "version": "0.1.0"}
        },
        "jsonrpc": "2.0",
        "id": 0
    }
    
    # 1. OAuth Bearer Token テスト
    print("\n🔐 テスト 1: OAuth Bearer Token 認証")
    try:
        # Bearer tokenを取得
        ssm_client = boto3.client('ssm', region_name=region)
        secrets_client = boto3.client('secretsmanager', region_name=region)
        
        # Cognito認証情報を取得
        secret_response = secrets_client.get_secret_value(SecretId='mcp_server/cognito/credentials')
        secret_data = json.loads(secret_response['SecretString'])
        bearer_token = secret_data['bearer_token']
        
        # curlコマンドを構築
        curl_cmd = [
            'curl', '-X', 'POST', url,
            '-H', 'Content-Type: application/json',
            '-H', 'Accept: application/json, text/event-stream',
            '-H', f'Authorization: Bearer {bearer_token}',
            '-d', json.dumps(test_payload),
            '-s', '-w', '%{http_code}',
            '-o', '/tmp/oauth_response.json'
        ]
        
        # curlを実行
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        http_code = result.stdout.strip()
        
        # レスポンスを読み取り
        try:
            with open('/tmp/oauth_response.json', 'r') as f:
                response_body = f.read()
        except:
            response_body = ""
        
        print(f"  HTTP Status: {http_code}")
        if response_body:
            try:
                response_json = json.loads(response_body)
                if 'message' in response_json:
                    print(f"  Message: {response_json['message']}")
            except:
                print(f"  Response: {response_body[:200]}...")
        
        oauth_success = http_code == '200'
        print(f"  結果: {'✅ 成功' if oauth_success else '❌ 失敗'}")
        
    except Exception as e:
        print(f"  ❌ OAuth テストエラー: {e}")
        oauth_success = False
    
    # 2. SigV4 認証テスト
    print("\n🔐 テスト 2: SigV4 認証")
    try:
        # AWS CLIを使用してSigV4署名付きリクエストを送信
        aws_cmd = [
            'aws', 'bedrock-agentcore-runtime', 'invoke-agent-runtime',
            '--agent-runtime-id', agent_arn.split('/')[-1],
            '--session-id', 'test-session-123',
            '--input-text', 'Hello, this is a test message',
            '--region', region,
            '--output', 'json'
        ]
        
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
            'awscurl', '--service', 'bedrock-agentcore',
            '--region', region,
            '-X', 'POST',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(test_payload),
            url
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
    print(f"\n📊 認証テスト結果:")
    print(f"  OAuth Bearer Token: {'✅ 動作' if oauth_success else '❌ 失敗'}")
    print(f"  SigV4 (AWS CLI):    {'✅ 動作' if sigv4_success else '❌ 失敗'}")
    print(f"  SigV4 (awscurl):    {'✅ 動作' if awscurl_success else '❌ 失敗'}")
    
    if oauth_success:
        recommended_auth = "OAuth Bearer Token"
        print(f"\n💡 推奨認証方法: {recommended_auth}")
        print("   simple_protocol_debug_client.py を使用してください")
    elif sigv4_success or awscurl_success:
        recommended_auth = "SigV4"
        print(f"\n💡 推奨認証方法: {recommended_auth}")
        print("   sigv4_mcp_client.py を使用してください")
    else:
        recommended_auth = "不明"
        print(f"\n❌ どの認証方法も動作しませんでした")
        print("   AgentCore Runtime の設定を確認してください")
    
    return {
        'oauth_success': oauth_success,
        'sigv4_success': sigv4_success,
        'awscurl_success': awscurl_success,
        'recommended_auth': recommended_auth
    }


def get_detailed_curl_command(agent_arn, region='us-east-1', auth_method='oauth'):
    """
    詳細なcurlコマンドを生成する
    """
    import urllib.parse
    import json
    
    # URLエンコード
    encoded_arn = urllib.parse.quote(agent_arn, safe='')
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    # テストペイロード
    test_payload = {
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "sampling": {},
                "roots": {"listChanged": True}
            },
            "clientInfo": {"name": "mcp", "version": "0.1.0"}
        },
        "jsonrpc": "2.0",
        "id": 0
    }
    
    if auth_method.lower() == 'oauth':
        # OAuth Bearer Token版
        curl_cmd = f'''curl -X POST \\
  "{url}" \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -H "Authorization: Bearer $(aws secretsmanager get-secret-value --secret-id 'mcp_server/cognito/credentials' --region {region} --query 'SecretString' --output text | jq -r '.bearer_token')" \\
  -d '{json.dumps(test_payload)}' \\
  -v'''
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
        result = subprocess.run(['pip', 'install', 'awscurl'], 
                              capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ awscurl のインストールが完了しました")
            return True
        else:
            print(f"❌ awscurl のインストールに失敗しました: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ awscurl のインストールエラー: {e}")
        return False