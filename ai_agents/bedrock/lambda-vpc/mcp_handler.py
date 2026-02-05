"""
MCP Protocol準拠のLambda関数（VPC内実行）
VPC内のリソース（RDS、ElastiCache等）にアクセス可能

検証ポイント：
1. VPC内LambdaがResponses APIから呼び出せるか
2. VPC情報がカスタム属性として確認できるか
3. パフォーマンスへの影響（コールドスタート）
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    VPC内Lambda Handler
    """
    logger.info(f"=== Lambda VPC Handler ===")
    logger.info(f"Event: {json.dumps(event, indent=2)}")
    logger.info(f"Context: request_id={context.aws_request_id}, function={context.function_name}")

    # JSON-RPC 2.0 パラメータ抽出
    jsonrpc = event.get('jsonrpc', '2.0')
    request_id = event.get('id', 'unknown')
    method = event.get('method')
    params = event.get('params', {})

    # カスタム属性の抽出
    custom_attributes = extract_custom_attributes(event)
    logger.info(f"Custom attributes: {json.dumps(custom_attributes)}")

    if method == 'tools/list':
        return handle_tools_list(jsonrpc, request_id, custom_attributes)
    elif method == 'tools/call':
        return handle_tools_call(jsonrpc, request_id, params, custom_attributes)
    else:
        return create_error_response(
            jsonrpc, request_id, -32601,
            f"Method not found: {method}",
            custom_attributes
        )


def extract_custom_attributes(event: Dict[str, Any]) -> Dict[str, Any]:
    """カスタム属性の抽出"""
    custom = {}
    for key in ['tenant_id', 'user_id', 'session_id', 'metadata', 'tags']:
        if key in event:
            custom[key] = event[key]
    params = event.get('params', {})
    if isinstance(params, dict):
        for key in ['tenant_id', 'user_id', 'session_id', 'metadata', 'tags']:
            if key in params:
                custom[key] = params[key]
    return custom


def handle_tools_list(
    jsonrpc: str,
    request_id: str,
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """tools/list処理"""
    logger.info("Handling tools/list request (VPC)")

    response = {
        "jsonrpc": jsonrpc,
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "vpc_info",
                    "description": "Get VPC execution environment information",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "boolean",
                                "description": "Include detailed information"
                            }
                        }
                    }
                },
                {
                    "name": "database_query",
                    "description": "Query VPC database (mock)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "get_weather",
                    "description": "Get weather (VPC version)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        },
                        "required": ["location"]
                    }
                }
            ]
        }
    }

    if custom_attributes:
        response['custom_attributes'] = custom_attributes
        response['result']['metadata'] = {
            "lambda_type": "vpc",
            "vpc_enabled": True,
            "received_attributes": list(custom_attributes.keys())
        }

    return response


def handle_tools_call(
    jsonrpc: str,
    request_id: str,
    params: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """tools/call処理"""
    tool_name = params.get('name')
    arguments = params.get('arguments', {})

    logger.info(f"Executing tool: {tool_name} (VPC)")

    try:
        if tool_name == 'vpc_info':
            result = execute_vpc_info_tool(arguments, custom_attributes)
        elif tool_name == 'database_query':
            result = execute_database_query_tool(arguments, custom_attributes)
        elif tool_name == 'get_weather':
            result = execute_weather_tool(arguments, custom_attributes)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        response = {
            "jsonrpc": jsonrpc,
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        }

        if custom_attributes:
            response['custom_attributes'] = custom_attributes

        return response

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}", exc_info=True)
        return create_error_response(
            jsonrpc, request_id, -32603,
            f"Internal error: {str(e)}",
            custom_attributes
        )


def execute_vpc_info_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """VPC情報取得ツール"""
    import os

    detail = arguments.get('detail', False)

    result = {
        "execution_environment": "VPC",
        "source": "lambda-vpc",
        "vpc_enabled": True
    }

    if detail:
        result['environment'] = {
            "AWS_REGION": os.getenv('AWS_REGION', 'unknown'),
            "AWS_EXECUTION_ENV": os.getenv('AWS_EXECUTION_ENV', 'unknown'),
            # VPC環境変数（存在する場合）
            "vpc_id": os.getenv('VPC_ID', 'configured_at_deployment'),
            "subnet_ids": os.getenv('SUBNET_IDS', 'configured_at_deployment')
        }

    if custom_attributes:
        result['custom_attributes'] = custom_attributes

    return result


def execute_database_query_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """データベースクエリツール（モック）"""
    query = arguments.get('query', '')

    # 本番環境ではここでRDSやElastiCacheに接続
    # 例: psycopg2でPostgreSQLに接続

    result = {
        "query": query,
        "result": "Mock result: VPC database accessible",
        "rows_affected": 0,
        "execution_time_ms": 15,
        "source": "lambda-vpc",
        "note": "In production, this would query RDS/Aurora in VPC"
    }

    if custom_attributes:
        result['custom_attributes'] = custom_attributes

    return result


def execute_weather_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """天気情報取得（VPC版）"""
    import random

    location = arguments.get('location', 'Unknown')

    result = {
        "location": location,
        "temperature": random.randint(10, 35),
        "unit": "celsius",
        "condition": random.choice(['Sunny', 'Cloudy', 'Rainy']),
        "source": "lambda-vpc",
        "vpc_enabled": True
    }

    if custom_attributes:
        result['custom_attributes'] = custom_attributes

    return result


def create_error_response(
    jsonrpc: str,
    request_id: str,
    error_code: int,
    error_message: str,
    custom_attributes: Dict[str, Any] = None
) -> Dict[str, Any]:
    """エラーレスポンス作成"""
    response = {
        "jsonrpc": jsonrpc,
        "id": request_id,
        "error": {
            "code": error_code,
            "message": error_message
        }
    }

    if custom_attributes:
        response['custom_attributes'] = custom_attributes

    return response
