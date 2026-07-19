"""
部署工具函数
不依赖外部库（纯标准库实现）
"""
import os
import re
from typing import Callable, Generic, TypeVar

T = TypeVar("T")

DEPLOY_CONFIG = "./config/deploy.yaml"
DEPLOY_TEMPLATE = "./deploy/template"


class cached_property(Generic[T]):
    """缓存属性装饰器（只计算一次）"""

    def __init__(self, func: Callable[..., T]):
        self.func = func

    def __get__(self, obj, cls) -> T:
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


def poor_yaml_read(file: str) -> dict:
    """
    简易 YAML 读取（不依赖 pyyaml）
    仅支持 key: value 顶层键值对
    """
    try:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {}

    data = {}
    regex = re.compile(r"^(.*?):(.*?)$")
    for line in content.splitlines():
        line = line.strip("\n\r\t ").replace("\\", "/")
        if line.startswith("#"):
            continue
        result = re.match(regex, line)
        if result:
            k, v = result.group(1).strip(), result.group(2).strip("\n\r\t' ")
            if v:
                if v.lower() == "null":
                    v = None
                elif v.lower() == "false":
                    v = False
                elif v.lower() == "true":
                    v = True
                elif v.isdigit():
                    v = int(v)
            data[k] = v
    return data


def poor_yaml_write(data: dict, file: str, template_file: str = DEPLOY_TEMPLATE) -> None:
    """基于模板写入 YAML（不依赖 pyyaml）"""
    try:
        with open(template_file, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return

    text = text.replace("\\", "/")
    for key, value in data.items():
        if value is None:
            value = "null"
        elif value is True:
            value = "true"
        elif value is False:
            value = "false"
        text = re.sub(f"{key}:.*?\n", f"{key}: {value}\n", text)

    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w", encoding="utf-8") as f:
        f.write(text)
