"""
OPC LLM 调用封装
支持 DeepSeek (Manager/Engineer) 和 MiniMax (QA)
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

try:
    from openai import OpenAI
except ImportError:
    print("请安装 openai: uv add openai")
    raise

from opc.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    MINIMAX_API_KEY, MINIMAX_BASE_URL, MINIMAX_MODEL,
)


class LLMClient:
    """LLM 客户端封装"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key:
            raise ValueError(f"API key 未设置")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
    
    def chat(self, messages: list, temperature: float = 0, **kwargs) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表 [{"role": "system"/"user"/"assistant", "content": "..."}]
            temperature: 温度参数，默认 0（稳定性优先）
        
        Returns:
            助手回复文本
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )
        return response.choices[0].message.content


def create_deepseek_client() -> LLMClient:
    """创建 DeepSeek 客户端（用于 Manager 和 Engineer）"""
    return LLMClient(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_MODEL,
    )


def create_minimax_client() -> LLMClient:
    """创建 MiniMax 客户端（用于 QA）"""
    return LLMClient(
        api_key=MINIMAX_API_KEY,
        base_url=MINIMAX_BASE_URL,
        model=MINIMAX_MODEL,
    )


def call_manager(messages: list) -> str:
    """调用 Manager"""
    client = create_deepseek_client()
    return client.chat(messages)


def call_engineer(messages: list) -> str:
    """调用 Engineer"""
    client = create_deepseek_client()
    return client.chat(messages)


def call_qa(messages: list) -> str:
    """调用 QA"""
    client = create_minimax_client()
    return client.chat(messages)
