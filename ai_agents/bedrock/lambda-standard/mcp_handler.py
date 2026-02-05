"""
MCP Protocol準拠のLambda関数（通常のLambda）
Responses APIから直接ARN指定で呼び出される

検証ポイント：
1. JSON-RPC 2.0プロトコル対応
2. カスタム属性（tenant_id, user_id等）の受け渡し
3. tools/list と tools/call の実装
"""

import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    MCP (Model Context Protocol) 準拠のLambda Handler
    """
    logger.info(f"=== Lambda Standard Handler ===")
    logger.info(f"Event: {json.dumps(event, indent=2)}")
    logger.info(f"Context: request_id={context.aws_request_id}, function={context.function_name}")

    # JSON-RPC 2.0 パラメータ抽出
    jsonrpc = event.get('jsonrpc', '2.0')
    request_id = event.get('id', 'unknown')
    method = event.get('method')
    params = event.get('params', {})

    # カスタム属性の抽出（検証ポイント）
    custom_attributes = extract_custom_attributes(event)
    logger.info(f"Custom attributes: {json.dumps(custom_attributes)}")

    # tools/list - 利用可能なツール一覧を返す
    if method == 'tools/list':
        return handle_tools_list(jsonrpc, request_id, custom_attributes)

    # tools/call - ツール実行
    elif method == 'tools/call':
        return handle_tools_call(jsonrpc, request_id, params, custom_attributes)

    # 未知のメソッド
    else:
        logger.warning(f"Unknown method: {method}")
        return create_error_response(
            jsonrpc, request_id, -32601,
            f"Method not found: {method}",
            custom_attributes
        )


def extract_custom_attributes(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    カスタム属性の抽出

    Responses APIから渡される可能性のあるカスタムフィールド：
    - tenant_id: テナント識別子
    - user_id: ユーザー識別子
    - session_id: セッション識別子
    - metadata: その他のメタデータ
    """
    custom = {}

    # 直接のフィールド
    for key in ['tenant_id', 'user_id', 'session_id', 'metadata', 'tags']:
        if key in event:
            custom[key] = event[key]

    # params内のカスタムフィールド
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
    logger.info("Handling tools/list request")

    response = {
        "jsonrpc": jsonrpc,
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get current weather for a specified location. Returns temperature, condition, humidity, and wind speed.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name, e.g., 'Tokyo', 'New York', 'London'"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "Temperature unit (default: celsius)"
                            }
                        },
                        "required": ["location"]
                    }
                },
                {
                    "name": "calculator",
                    "description": "Evaluate a mathematical expression. Supports basic arithmetic operations.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Mathematical expression, e.g., '2 + 2', '10 * 5', '(3 + 7) / 2'"
                            }
                        },
                        "required": ["expression"]
                    }
                },
                {
                    "name": "echo_metadata",
                    "description": "Echo back custom attributes to verify metadata propagation",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Message to echo back"
                            }
                        },
                        "required": ["message"]
                    }
                }
            ]
        }
    }

    # カスタム属性をレスポンスに追加（検証ポイント）
    if custom_attributes:
        response['custom_attributes'] = custom_attributes
        response['result']['metadata'] = {
            "lambda_type": "standard",
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

    logger.info(f"Executing tool: {tool_name}")
    logger.info(f"Arguments: {json.dumps(arguments)}")

    try:
        # ツール実行
        if tool_name == 'get_weather':
            result = execute_weather_tool(arguments, custom_attributes)
        elif tool_name == 'calculator':
            result = execute_calculator_tool(arguments, custom_attributes)
        elif tool_name == 'echo_metadata':
            result = execute_echo_metadata_tool(arguments, custom_attributes)
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

        # カスタム属性をレスポンスに追加
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


def execute_weather_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """天気情報を取得（モック実装）"""
    import random

    location = arguments.get('location', 'Unknown')
    unit = arguments.get('unit', 'celsius')

    temperature = random.randint(10, 35)
    if unit == 'fahrenheit':
        temperature = int(temperature * 9 / 5 + 32)

    conditions = ['Sunny', 'Cloudy', 'Rainy', 'Partly Cloudy', 'Clear']

    result = {
        "location": location,
        "temperature": temperature,
        "unit": unit,
        "condition": random.choice(conditions),
        "humidity": random.randint(40, 80),
        "wind_speed": random.randint(5, 25),
        "source": "lambda-standard",
        "timestamp": "2026-02-05T12:00:00Z"
    }

    # カスタム属性を結果に含める
    if custom_attributes:
        result['custom_attributes'] = custom_attributes

    return result


def execute_calculator_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """計算機ツール"""
    expression = arguments.get('expression', '')

    try:
        # 安全な評価（許可された文字のみ）
        sanitized = ''.join(c for c in expression if c in '0123456789+-*/(). ')
        if not sanitized:
            raise ValueError("Empty expression")

        result_value = eval(sanitized)

        result = {
            "expression": expression,
            "result": float(result_value),
            "source": "lambda-standard"
        }

        # カスタム属性を結果に含める
        if custom_attributes:
            result['custom_attributes'] = custom_attributes

        return result

    except Exception as e:
        raise ValueError(f"Invalid expression: {str(e)}")


def execute_echo_metadata_tool(
    arguments: Dict[str, Any],
    custom_attributes: Dict[str, Any]
) -> Dict[str, Any]:
    """メタデータエコーツール（検証用）"""
    message = arguments.get('message', '')

    return {
        "message": message,
        "echo": f"Received: {message}",
        "custom_attributes": custom_attributes,
        "source": "lambda-standard",
        "verification": "Custom attributes successfully propagated"
    }


def create_error_response(
    jsonrpc: str,
    request_id: str,
    error_code: int,
    error_message: str,
    custom_attributes: Optional[Dict[str, Any]] = None
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
