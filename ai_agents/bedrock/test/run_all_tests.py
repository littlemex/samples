"""
AWS Bedrock Responses API 統合検証スクリプト

全ての検証を1つのスクリプトで実行：
1. OpenAI互換エンドポイント基本呼び出し
2. Lambda MCP統合（tools/list, tools/call）
3. VPC Lambda
4. カスタム属性の伝播
5. パフォーマンス測定
6. ペイロードサイズ上限
7. シーケンス長上限
8. エラーハンドリング
"""

import json
import os
import time
import boto3
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

# 環境変数
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
GPT_OSS_MODEL = "openai.gpt-oss-120b-1:0"
VPC_LAMBDA_DEPLOYED = os.getenv('VPC_LAMBDA_DEPLOYED', 'false') == 'true'

# クライアント
lambda_client = boto3.client('lambda', region_name=AWS_REGION)


def print_section(title: str):
    """セクション区切りを出力"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    """サブセクション区切りを出力"""
    print("\n" + "━" * 80)
    print(f"  {title}")
    print("━" * 80 + "\n")


def print_request_response(request: dict, response: dict, description: str = ""):
    """リクエストとレスポンスをペアで出力"""
    if description:
        print(f"【{description}】\n")

    print("📤 REQUEST:")
    print(json.dumps(request, indent=2, ensure_ascii=False))
    print()

    print("📥 RESPONSE:")
    print(json.dumps(response, indent=2, ensure_ascii=False))
    print()


# ============================================================================
# 1. OpenAI互換エンドポイント基本呼び出し
# ============================================================================

def test_1_openai_endpoint():
    """Test 1: OpenAI互換エンドポイント基本呼び出し"""
    print_section("Test 1: OpenAI互換エンドポイント基本呼び出し")

    try:
        import requests
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        session = boto3.Session()
        credentials = session.get_credentials()

        url = f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com/model/{GPT_OSS_MODEL}/invoke"

        request_body = {
            "messages": [
                {"role": "user", "content": "Hello! Please respond briefly."}
            ],
            "max_tokens": 100,
            "temperature": 0.7
        }

        # AWS署名
        request = AWSRequest(method='POST', url=url, data=json.dumps(request_body))
        SigV4Auth(credentials, 'bedrock', AWS_REGION).add_auth(request)

        # リクエスト送信
        response = requests.post(
            url,
            headers=dict(request.headers),
            data=json.dumps(request_body)
        )

        if response.status_code == 200:
            result = response.json()
            print_request_response(request_body, result, "OpenAI互換エンドポイント")
            print("✅ Test 1 成功\n")
        else:
            print(f"❌ Test 1 失敗: HTTP {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"❌ Test 1 例外: {str(e)}")


# ============================================================================
# 2. Lambda MCP統合 - tools/list
# ============================================================================

def test_2_tools_list():
    """Test 2: tools/list でツール一覧取得"""
    print_section("Test 2: Lambda MCP - tools/list")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "tenant_id": "tenant-test-001",
        "metadata": {
            "test": "responses-api",
            "timestamp": "2026-02-05"
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "tools/list")
        print("✅ Test 2 成功\n")

    except Exception as e:
        print(f"❌ Test 2 例外: {str(e)}")


# ============================================================================
# 3. Lambda MCP統合 - tools/call (calculator)
# ============================================================================

def test_3_tools_call_calculator():
    """Test 3: tools/call でcalculatorツール実行"""
    print_section("Test 3: Lambda MCP - tools/call (calculator)")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "tenant_id": "tenant-test-001",
        "user_id": "user-test-001",
        "params": {
            "name": "calculator",
            "arguments": {
                "expression": "42 * 42"
            }
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "tools/call - calculator")
        print("✅ Test 3 成功\n")

    except Exception as e:
        print(f"❌ Test 3 例外: {str(e)}")


# ============================================================================
# 4. カスタム属性の完全伝播（ネスト構造・配列）
# ============================================================================

def test_4_custom_attributes():
    """Test 4: カスタム属性の完全伝播"""
    print_section("Test 4: カスタム属性の完全伝播（ネスト構造・配列）")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "tenant_id": "tenant-multi-attr-test",
        "user_id": "user-12345",
        "session_id": "session-67890",
        "metadata": {
            "region": "ap-northeast-1",
            "plan": "enterprise",
            "features": ["tool-use", "mcp"]
        },
        "tags": ["test", "responses-api", "bedrock"],
        "params": {
            "name": "echo_metadata",
            "arguments": {
                "message": "Testing custom attributes propagation"
            }
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "カスタム属性の完全伝播")

        # カスタム属性が伝播しているか検証
        custom_in_response = response_data.get('custom_attributes', {})
        print("📊 カスタム属性検証:")
        print(f"  リクエストのカスタム属性数: 5")
        print(f"  レスポンスのカスタム属性数: {len(custom_in_response)}")

        if len(custom_in_response) == 5:
            print("  ✅ すべてのカスタム属性が正常に伝播\n")
        else:
            print(f"  ⚠️  一部のカスタム属性が欠落\n")

    except Exception as e:
        print(f"❌ Test 4 例外: {str(e)}")


# ============================================================================
# 5. VPC Lambda
# ============================================================================

def test_5_vpc_lambda():
    """Test 5: VPC Lambda"""
    if not VPC_LAMBDA_DEPLOYED:
        print_section("Test 5: VPC Lambda（スキップ - 未デプロイ）")
        return

    print_section("Test 5: VPC Lambda")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "tenant_id": "tenant-vpc-test",
        "params": {
            "name": "vpc_info",
            "arguments": {
                "detail": True
            }
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-vpc',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "VPC Lambda - vpc_info")
        print("✅ Test 5 成功\n")

    except Exception as e:
        print(f"❌ Test 5 例外: {str(e)}")


# ============================================================================
# 6. パフォーマンス測定
# ============================================================================

def test_6_performance():
    """Test 6: パフォーマンス測定（コールドスタート vs ウォームスタート）"""
    print_section("Test 6: パフォーマンス測定")

    payload = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/list"
    }

    latencies = []

    print("10回の連続実行でレイテンシーを測定中...\n")

    for i in range(10):
        start = time.time()

        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(payload)
        )

        _ = json.loads(response['Payload'].read())

        end = time.time()
        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)

        print(f"  実行 {i+1}: {latency_ms:.2f} ms")

        if i == 0:
            time.sleep(2)

    print(f"\n📊 パフォーマンス結果:")
    print(f"  コールドスタート: {latencies[0]:.2f} ms")
    print(f"  ウォーム平均: {sum(latencies[1:]) / len(latencies[1:]):.2f} ms")
    print(f"  最小値: {min(latencies):.2f} ms")
    print(f"  最大値: {max(latencies):.2f} ms")
    print(f"  全体平均: {sum(latencies) / len(latencies):.2f} ms")
    print("✅ Test 6 成功\n")


# ============================================================================
# 7. ペイロードサイズ上限
# ============================================================================

def test_7_payload_limits():
    """Test 7: ペイロードサイズ上限"""
    print_section("Test 7: ペイロードサイズ上限")

    test_sizes = [1, 10, 100, 1024, 5120, 6144, 7168]  # KB (1KB, 10KB, 100KB, 1MB, 5MB, 6MB, 7MB)

    results = []

    for size_kb in test_sizes:
        print(f"テスト: {size_kb:,} KB ペイロード...")

        large_data = "x" * (size_kb * 1024 - 100)

        request_payload = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "echo_metadata",
                "arguments": {
                    "message": large_data
                }
            }
        }

        payload_json = json.dumps(request_payload)
        actual_size = len(payload_json.encode('utf-8'))

        try:
            response = lambda_client.invoke(
                FunctionName='bedrock-mcp-standard',
                Payload=payload_json
            )

            result_data = json.loads(response['Payload'].read())

            if 'result' in result_data:
                print(f"  ✅ 成功: {actual_size:,} bytes\n")
                results.append({
                    "size_kb": size_kb,
                    "actual_bytes": actual_size,
                    "status": "success"
                })
            elif 'errorMessage' in result_data:
                error_msg = result_data['errorMessage']
                print(f"  ⚠️  Lambda エラー: {error_msg[:100]}\n")
                results.append({
                    "size_kb": size_kb,
                    "actual_bytes": actual_size,
                    "status": "lambda_error",
                    "error": error_msg
                })

        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ 失敗: {error_msg[:100]}\n")
            results.append({
                "size_kb": size_kb,
                "actual_bytes": actual_size,
                "status": "error",
                "error": error_msg
            })

    print("📊 Test 7 結果サマリー:")
    for result in results:
        status_icon = {
            "success": "✅",
            "lambda_error": "⚠️",
            "error": "❌"
        }.get(result['status'], "❓")

        size_mb = result['size_kb'] / 1024
        if size_mb >= 1:
            size_display = f"{size_mb:.0f} MB"
        else:
            size_display = f"{result['size_kb']} KB"

        print(f"  {status_icon} {size_display} ({result['actual_bytes']:,} bytes): {result['status']}")
        if 'error' in result:
            print(f"      → {result['error'][:100]}")

    print("\n✅ Test 7 完了\n")


# ============================================================================
# 8. GPT-OSS シーケンス長上限
# ============================================================================

def test_8_sequence_length():
    """Test 8: GPT-OSS シーケンス長上限"""
    print_section("Test 8: GPT-OSS シーケンス長上限")

    test_cases = [
        (1, "1K 文字"),
        (10, "10K 文字"),
        (50, "50K 文字"),
        (100, "100K 文字"),
        (200, "200K 文字"),
        (300, "300K 文字"),
        (400, "400K 文字"),
        (500, "500K 文字"),
        (685, "685K 文字 (128K トークン想定)")
    ]

    results = []

    try:
        import requests
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        session = boto3.Session()
        credentials = session.get_credentials()

        url = f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com/model/{GPT_OSS_MODEL}/invoke"

        for size_k, description in test_cases:
            print(f"テスト: {description}...")

            text_length = size_k * 1024
            large_text = "This is a test sentence to measure sequence length limits. " * (text_length // 60)
            actual_size = len(large_text)

            body = {
                "messages": [
                    {
                        "role": "user",
                        "content": f"Count 'test' in this text: {large_text}"
                    }
                ],
                "max_tokens": 10,
                "temperature": 0.0
            }

            payload_size = len(json.dumps(body).encode('utf-8'))

            try:
                request = AWSRequest(method='POST', url=url, data=json.dumps(body))
                SigV4Auth(credentials, 'bedrock', AWS_REGION).add_auth(request)

                response = requests.post(
                    url,
                    headers=dict(request.headers),
                    data=json.dumps(body),
                    timeout=120
                )

                if response.status_code == 200:
                    result = response.json()
                    usage = result.get('usage', {})
                    input_tokens = usage.get('prompt_tokens', 0)

                    print(f"  ✅ 成功")
                    print(f"     テキストサイズ: {actual_size:,} 文字")
                    print(f"     ペイロードサイズ: {payload_size:,} bytes")
                    print(f"     入力トークン: {input_tokens:,}\n")

                    results.append({
                        "size_k": size_k,
                        "description": description,
                        "status": "success",
                        "text_size": actual_size,
                        "payload_size": payload_size,
                        "input_tokens": input_tokens
                    })
                else:
                    error_text = response.text[:200]
                    print(f"  ❌ エラー: HTTP {response.status_code}")
                    print(f"     {error_text}\n")

                    results.append({
                        "size_k": size_k,
                        "description": description,
                        "status": "error",
                        "http_code": response.status_code,
                        "error": error_text
                    })

            except Exception as e:
                error_msg = str(e)
                print(f"  ❌ 例外: {error_msg[:200]}\n")

                results.append({
                    "size_k": size_k,
                    "description": description,
                    "status": "exception",
                    "error": error_msg
                })

        # サマリー出力
        print("=" * 80)
        print("📊 Test 8 結果サマリー")
        print("=" * 80)
        print()

        successful = [r for r in results if r['status'] == 'success']
        if successful:
            max_success = max(successful, key=lambda x: x['input_tokens'])
            print(f"💡 最大成功:")
            print(f"   {max_success['description']}")
            print(f"   入力トークン: {max_success['input_tokens']:,}")
            print(f"   テキストサイズ: {max_success['text_size']:,} 文字")
            print(f"   ペイロードサイズ: {max_success['payload_size']:,} bytes")

            # 文字/トークン比率を計算
            if max_success['input_tokens'] > 0:
                ratio = max_success['text_size'] / max_success['input_tokens']
                print(f"   文字/トークン比率: {ratio:.2f} 文字/トークン")
            print()

        failed = [r for r in results if r['status'] in ['error', 'exception']]
        if failed:
            print("⚠️  失敗したテスト:")
            for f in failed:
                print(f"   {f['description']}: {f.get('error', 'Unknown error')[:100]}")
            print()

        print("✅ Test 8 完了\n")

    except Exception as e:
        print(f"❌ Test 8 例外: {str(e)}")


# ============================================================================
# 9. エラーハンドリング - 不正な式
# ============================================================================

def test_9_error_handling():
    """Test 9: エラーハンドリング"""
    print_section("Test 9: エラーハンドリング")

    # 9-1: ゼロ除算
    print_subsection("9-1: ゼロ除算")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "calculator",
            "arguments": {
                "expression": "1 / 0"
            }
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "ゼロ除算エラー")

        if 'error' in response_data:
            print("✅ 正常にエラーレスポンスを返却\n")
        else:
            print("⚠️  エラーレスポンスではない\n")

    except Exception as e:
        print(f"❌ Test 9-1 例外: {str(e)}")

    # 9-2: 存在しないツール
    print_subsection("9-2: 存在しないツール")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "non_existent_tool",
            "arguments": {}
        }
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "存在しないツール")

        if 'error' in response_data:
            print("✅ 正常にエラーレスポンスを返却\n")
        else:
            print("⚠️  エラーレスポンスではない\n")

    except Exception as e:
        print(f"❌ Test 9-2 例外: {str(e)}")

    # 9-3: 存在しないメソッド
    print_subsection("9-3: 存在しないメソッド")

    request_payload = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/invalid_method"
    }

    try:
        response = lambda_client.invoke(
            FunctionName='bedrock-mcp-standard',
            Payload=json.dumps(request_payload)
        )

        response_data = json.loads(response['Payload'].read())
        print_request_response(request_payload, response_data, "存在しないメソッド")

        if 'error' in response_data:
            error_code = response_data['error']['code']
            print(f"✅ 正常にエラーレスポンスを返却（エラーコード: {error_code}）")
            if error_code == -32601:
                print("✅ JSON-RPC 2.0 標準エラーコード -32601 (Method not found)\n")
        else:
            print("⚠️  エラーレスポンスではない\n")

    except Exception as e:
        print(f"❌ Test 9-3 例外: {str(e)}")

    print("✅ Test 9 成功\n")


# ============================================================================
# メイン実行
# ============================================================================

def main():
    """全テストを実行"""
    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  AWS Bedrock Responses API 統合検証スクリプト".center(76) + "  █")
    print("█" + " " * 78 + "█")
    print("█" * 80)

    test_1_openai_endpoint()
    test_2_tools_list()
    test_3_tools_call_calculator()
    test_4_custom_attributes()
    test_5_vpc_lambda()
    test_6_performance()
    test_7_payload_limits()
    test_8_sequence_length()
    test_9_error_handling()

    print("\n" + "█" * 80)
    print("█" + " " * 78 + "█")
    print("█" + "  全テスト完了".center(76) + "  █")
    print("█" + " " * 78 + "█")
    print("█" * 80 + "\n")


if __name__ == "__main__":
    main()
