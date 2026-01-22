"""
オンラインサービングのサンプル

FastAPIを使用したMulti-LoRA推論APIサーバーです。
"""

import argparse
import os
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


# リクエスト/レスポンスモデル
class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Input prompt for generation")
    lora_adapter: Optional[str] = Field(None, description="LoRA adapter name to use")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.95, ge=0.0, le=1.0, description="Top-p sampling value")
    max_tokens: int = Field(512, ge=1, le=2048, description="Maximum tokens to generate")


class GenerateResponse(BaseModel):
    generated_text: str
    num_tokens: int
    lora_adapter: Optional[str]


class BatchGenerateRequest(BaseModel):
    requests: List[GenerateRequest]


class BatchGenerateResponse(BaseModel):
    results: List[GenerateResponse]


# グローバル変数
llm: Optional[LLM] = None
lora_adapters: Dict[str, str] = {}


def initialize_llm(
    model_name: str,
    max_loras: int = 4,
    max_lora_rank: int = 64,
):
    """LLMエンジンを初期化"""
    global llm

    print(f"Initializing LLM: {model_name}")
    llm = LLM(
        model=model_name,
        enable_lora=True,
        max_loras=max_loras,
        max_lora_rank=max_lora_rank,
        max_cpu_loras=max_loras * 2,
        gpu_memory_utilization=0.85,
    )
    print("LLM initialized successfully")


def register_lora_adapters(adapters: Dict[str, str]):
    """LoRAアダプターを登録"""
    global lora_adapters

    for name, path in adapters.items():
        if os.path.exists(path):
            lora_adapters[name] = path
            print(f"Registered LoRA adapter: {name} -> {path}")
        else:
            print(f"Warning: LoRA adapter path not found: {path}")


# FastAPIアプリケーション
app = FastAPI(
    title="vLLM Multi-LoRA Inference API",
    description="API server for Multi-LoRA inference with vLLM",
    version="1.0.0",
)


@app.get("/")
def root():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "running",
        "available_loras": list(lora_adapters.keys()),
    }


@app.get("/lora-adapters")
def list_lora_adapters():
    """利用可能なLoRAアダプターのリスト"""
    return {
        "adapters": [
            {"name": name, "path": path}
            for name, path in lora_adapters.items()
        ]
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest):
    """単一プロンプトの推論"""
    if llm is None:
        raise HTTPException(status_code=500, detail="LLM not initialized")

    # サンプリングパラメータ
    sampling_params = SamplingParams(
        temperature=request.temperature,
        top_p=request.top_p,
        max_tokens=request.max_tokens,
    )

    # LoRAリクエストの作成
    lora_request = None
    if request.lora_adapter:
        if request.lora_adapter not in lora_adapters:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown LoRA adapter: {request.lora_adapter}",
            )

        lora_request = LoRARequest(
            lora_name=request.lora_adapter,
            lora_int_id=hash(request.lora_adapter) % (2**31),
            lora_local_path=lora_adapters[request.lora_adapter],
        )

    # 推論実行
    outputs = llm.generate(
        [(request.prompt, sampling_params, lora_request)]
    )

    output = outputs[0]
    generated_text = output.outputs[0].text
    num_tokens = len(output.outputs[0].token_ids)

    return GenerateResponse(
        generated_text=generated_text,
        num_tokens=num_tokens,
        lora_adapter=request.lora_adapter,
    )


@app.post("/batch-generate", response_model=BatchGenerateResponse)
def batch_generate(batch_request: BatchGenerateRequest):
    """複数プロンプトのバッチ推論"""
    if llm is None:
        raise HTTPException(status_code=500, detail="LLM not initialized")

    # バッチリクエストを準備
    requests = []
    for req in batch_request.requests:
        sampling_params = SamplingParams(
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
        )

        # LoRAリクエストの作成
        lora_request = None
        if req.lora_adapter:
            if req.lora_adapter not in lora_adapters:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown LoRA adapter: {req.lora_adapter}",
                )

            lora_request = LoRARequest(
                lora_name=req.lora_adapter,
                lora_int_id=hash(req.lora_adapter) % (2**31),
                lora_local_path=lora_adapters[req.lora_adapter],
            )

        requests.append((req.prompt, sampling_params, lora_request))

    # バッチ推論実行
    outputs = llm.generate(requests)

    # 結果を整形
    results = []
    for i, output in enumerate(outputs):
        generated_text = output.outputs[0].text
        num_tokens = len(output.outputs[0].token_ids)

        results.append(
            GenerateResponse(
                generated_text=generated_text,
                num_tokens=num_tokens,
                lora_adapter=batch_request.requests[i].lora_adapter,
            )
        )

    return BatchGenerateResponse(results=results)


def main():
    parser = argparse.ArgumentParser(description="vLLM Multi-LoRA Serving API")
    parser.add_argument(
        "--model",
        type=str,
        default="meta-llama/Llama-2-7b-hf",
        help="Base model name or path",
    )
    parser.add_argument(
        "--max-loras",
        type=int,
        default=4,
        help="Maximum number of concurrent LoRAs",
    )
    parser.add_argument(
        "--max-lora-rank",
        type=int,
        default=64,
        help="Maximum LoRA rank",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server",
    )

    args = parser.parse_args()

    # LLMを初期化
    initialize_llm(
        model_name=args.model,
        max_loras=args.max_loras,
        max_lora_rank=args.max_lora_rank,
    )

    # LoRAアダプターを登録
    adapters = {
        "sql": "./lora_adapters/sql-lora",
        "python": "./lora_adapters/python-lora",
        "math": "./lora_adapters/math-lora",
    }
    register_lora_adapters(adapters)

    # サーバーを起動
    print(f"\nStarting server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
