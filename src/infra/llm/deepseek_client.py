"""
DeepSeek LLM 客户端

使用 OpenAI 兼容的 API
"""

import os
import json
import asyncio
from typing import Optional
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """DeepSeek LLM 客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat"
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment")

        # 初始化客户端
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        logger.info(f"DeepSeekClient initialized with model={model}")

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        生成响应

        Args:
            prompt: 输入提示
            **kwargs: 额外参数（temperature, max_tokens 等）

        Returns:
            生成的文本
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 2048)
            )

            content = response.choices[0].message.content
            logger.debug(f"Generated response: {content[:100]}...")

            return content

        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

    async def generate_json(self, prompt: str, **kwargs) -> dict:
        """
        生成 JSON 响应

        尝试解析响应为 JSON，失败则抛出异常
        """
        response = await self.generate(prompt, **kwargs)

        # 尝试提取 JSON（可能包含在 ```json 代码块中）
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {response[:200]}")
            raise ValueError(f"Response is not valid JSON: {e}")
