"""dotenv.py — 零依赖的 .env 文件加载器
纯 Python 标准库解析，无需 python-dotenv 包。
"""

import os
import re


def load_dotenv(path: str | None = None) -> bool:
    """加载 .env 文件到环境变量

    规则:
    - 不覆盖已有的环境变量（export 优先级 > .env）
    - 支持 # 注释
    - 支持 KEY=VALUE、KEY="VALUE"、KEY='VALUE'
    - 自动在 CWD 和项目根目录查找 .env

    返回 True 表示成功加载了文件
    """
    if path is None:
        path = _find_dotenv()

    if not path or not os.path.exists(path):
        return False

    loaded = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue

            match = re.match(r"^([\w_]+)\s*=\s*(.*?)$", line)
            if not match:
                continue

            key = match.group(1)
            value = match.group(2)

            # 去掉引号
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]

            # 不覆盖已有环境变量
            if key not in os.environ:
                os.environ[key] = value
                loaded = True

    return loaded


def _find_dotenv() -> str | None:
    """从 CWD 向上查找 .env 文件"""
    cwd = os.getcwd()

    # 先在当前目录找
    candidate = os.path.join(cwd, ".env")
    if os.path.exists(candidate):
        return candidate

    # 再往上翻一级（适配 src/ 下启动的情况）
    parent = os.path.dirname(cwd)
    candidate = os.path.join(parent, ".env")
    if os.path.exists(candidate):
        return candidate

    return None
