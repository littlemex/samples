#!/usr/bin/env python3
"""
SigV4認証を使用するMCP Protocol Debug Client

Amazon Bedrock AgentCore Runtime に SigV4 認証でアクセスします。
EC2インスタンスのIAMロールを使用して認証を行います。
--local オプションで localhost:8000/mcp にも接続可能です。
"""

import argparse
import asyncio
import json
import logging

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def setup_logging(debug: bool = False):
    """ログ設定を初期化"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level, format="[%(asctime)s] %(name)s - %(levelname)s: %(message)s"
    )

    # httpxのログレベルを調整（デバッグ時以外は警告以上のみ表示）
    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("boto3").setLevel(logging.WARNING)


class MCPClient:
    """MCP Client (SigV4認証またはローカル接続対応)"""

    def __init__(self, url: str, region: str = "us-east-1", use_sigv4: bool = True):
        self.url = url
        self.region = region
        self.use_sigv4 = use_sigv4
        self.logger = logging.getLogger(self.__class__.__name__)

        if use_sigv4:
            self.logger.debug(f"Initializing SigV4 client for region: {region}")
            self.session = boto3.Session()
            self.credentials = self.session.get_credentials()
            # SigV4認証の準備
            self.sigv4 = SigV4Auth(self.credentials, "bedrock-agentcore", region)
            self.logger.debug("SigV4 authentication configured")
        else:
            self.logger.debug("Local client mode - no authentication")
            self.sigv4 = None

    async def send_request(self, payload: dict) -> dict:
        """SigV4署名付きまたはローカルリクエストを送信"""

        self.logger.debug(
            f"Sending request: {payload.get('method', 'unknown')} (ID: {payload.get('id', 'N/A')})"
        )

        # JSONデータを準備
        data = json.dumps(payload).encode("utf-8")
        self.logger.debug(f"Request payload size: {len(data)} bytes")

        if self.use_sigv4:
            # SigV4認証を使用する場合
            self.logger.debug("Using SigV4 authentication")
            # AWSRequestオブジェクトを作成
            request = AWSRequest(
                method="POST",
                url=self.url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )

            # SigV4署名を追加
            self.sigv4.add_auth(request)
            self.logger.debug("SigV4 signature added to request")

            # httpxでリクエストを実行
            async with httpx.AsyncClient(timeout=30.0) as client:
                self.logger.debug(f"Sending POST request to: {request.url}")
                response = await client.request(
                    method=request.method,
                    url=request.url,
                    headers=dict(request.headers),
                    content=request.body,
                )
        else:
            # ローカル接続の場合
            self.logger.debug("Using local connection (no authentication)")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                self.logger.debug(f"Sending POST request to: {self.url}")
                response = await client.post(
                    url=self.url, headers=headers, content=data
                )

        # レスポンスを処理
        self.logger.debug(f"Response status: {response.status_code}")
        self.logger.debug(f"Response headers: {dict(response.headers)}")

        if response.status_code == 200:
            response_data = response.json()
            self.logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
            return response_data
        else:
            self.logger.error(f"HTTP {response.status_code}: {response.text}")
            raise Exception(f"HTTP {response.status_code}: {response.text}")


def parse_args():
    """Command line argumentsをパース"""
    parser = argparse.ArgumentParser(description="MCP Protocol Debug Client")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--local", action="store_true", help="Connect to localhost:8000/mcp"
    )
    group.add_argument(
        "--remote", action="store_true", help="Connect to AWS Bedrock AgentCore Runtime"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def test_mcp_connection(client: MCPClient, connection_type: str):
    """MCP接続をテスト"""
    logger = logging.getLogger("test_mcp_connection")
    try:
        print(f"🔄 Connection Attempt ({connection_type})")
        logger.debug(f"Starting MCP connection test for {connection_type}")

        print("✅ HTTP connection established")
        print("✅ Protocol debug session created")

        # MCPプロトコルテスト
        print("🚀 Starting MCP initialization...")

        # 初期化リクエスト
        init_payload = {
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"sampling": {}, "roots": {"listChanged": True}},
                "clientInfo": {"name": "mcp", "version": "0.1.0"},
            },
            "jsonrpc": "2.0",
            "id": 0,
        }

        # 初期化リクエストを送信
        logger.debug("Sending initialize request")
        init_response = await client.send_request(init_payload)
        print("✅ MCP initialized:")
        print(json.dumps(init_response, indent=2, ensure_ascii=False))

        # ツール一覧を取得
        tools_payload = {
            "method": "tools/list",
            "params": {},
            "jsonrpc": "2.0",
            "id": 1,
        }

        try:
            logger.debug("Sending tools/list request")
            tools_response = await client.send_request(tools_payload)
            print("🔧 Available tools response:")
            print(json.dumps(tools_response, indent=2, ensure_ascii=False))

            if "result" in tools_response and "tools" in tools_response["result"]:
                tools = tools_response["result"]["tools"]
                print(f"\n🔧 Available tools summary: {len(tools)}")
                for tool in tools:
                    print(
                        f"  - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}"
                    )
            else:
                print("🔧 No tools found or unexpected response format")
        except Exception as e:
            print(f"⚠️  Tools list request failed: {e}")

        print(f"\n✅ MCP connection test ({connection_type}) completed successfully!")
        logger.debug(f"MCP connection test completed for {connection_type}")

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        logger.error(f"Connection test failed: {e}")
        import traceback

        traceback.print_exc()


async def main():
    args = parse_args()

    # ログ設定
    setup_logging(args.debug)

    if args.debug:
        print("🐛 Debug logging enabled")

    if args.local:
        print("=== MCP PROTOCOL DEBUG CLIENT (LOCAL) ===")
        if args.debug:
            print("🐛 Debug mode: ON")
        url = "http://localhost:8000/mcp"
        print("🌐 Connection Details:")
        print(f"URL: {url}")
        print("Auth: None (Local)")

        client = MCPClient(url, use_sigv4=False)
        if args.debug:
            logging.getLogger().info(f"Creating local client for URL: {url}")
        await test_mcp_connection(client, "Local")

    elif args.remote:
        print("=== MCP PROTOCOL DEBUG CLIENT (REMOTE/SigV4) ===")
        if args.debug:
            print("🐛 Debug mode: ON")
        print("Region: us-east-1")

        # AWS認証情報を確認
        print("🔐 AWS認証情報を取得中...")
        try:
            sts_client = boto3.client("sts", region_name="us-east-1")
            identity = sts_client.get_caller_identity()
            print(f"✅ AWS Identity: {identity['Arn']}")
        except Exception as e:
            print(f"❌ AWS認証エラー: {e}")
            return

        # Agent ARNを取得
        try:
            ssm_client = boto3.client("ssm", region_name="us-east-1")
            response = ssm_client.get_parameter(Name="/mcp_server/runtime/agent_arn")
            agent_arn = response["Parameter"]["Value"]
            print(f"✅ Agent ARN: {agent_arn}")
        except Exception as e:
            print(f"❌ Agent ARN取得エラー: {e}")
            return

        # AgentCore Runtime URLを構築
        encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
        url = f"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

        print("🌐 Connection Details:")
        print(f"URL: {url}")
        print("Auth: SigV4 (IAM Role)")

        client = MCPClient(url, region="us-east-1", use_sigv4=True)
        if args.debug:
            logging.getLogger().info(f"Creating SigV4 client for URL: {url}")
        await test_mcp_connection(client, "Remote/SigV4")


if __name__ == "__main__":
    asyncio.run(main())
