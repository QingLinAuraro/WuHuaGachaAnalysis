"""
依赖管理（pip install）
"""
import os
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from deploy.config import DeployConfig
from deploy.utils import cached_property


@dataclass
class Dependency:
    name: str
    version: str

    def __post_init__(self):
        self.name = re.sub(r"\[.*\]", "", self.name)
        self.name = self.name.replace("_", "-").strip().lower()
        self.version = self.version.strip()

    @property
    def pretty_name(self) -> str:
        return f"{self.name}=={self.version}"

    def __str__(self):
        return self.pretty_name

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


class PipManager(DeployConfig):
    @cached_property
    def python(self) -> str:
        return sys.executable.replace("\\", "/")

    @cached_property
    def requirements_file(self) -> str:
        if self.RequirementsFile == "requirements.txt":
            return "requirements.txt"
        return self.filepath("RequirementsFile")

    @cached_property
    def pip(self) -> str:
        return f'"{self.python}" -m pip'

    @cached_property
    def python_site_packages(self) -> str:
        import site

        for path in site.getsitepackages():
            if path.endswith("site-packages"):
                return path
        return site.getsitepackages()[0]

    @cached_property
    def installed_deps(self) -> set:
        data = set()
        regex = re.compile(r"(.*)-(.*).dist-info")
        try:
            for name in os.listdir(self.python_site_packages):
                m = regex.search(name)
                if m:
                    data.add(Dependency(name=m.group(1), version=m.group(2)))
        except FileNotFoundError:
            pass
        return data

    @cached_property
    def required_deps(self) -> set:
        data = set()
        # 简单解析 requirements.txt: name==version 或 name>=version
        regex = re.compile(r"^([a-zA-Z0-9_.-]+)\s*([><=!~]+)\s*([0-9.]+)")
        try:
            with open(self.requirements_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = regex.match(line)
                    if m:
                        data.add(Dependency(name=m.group(1), version=m.group(3)))
        except FileNotFoundError:
            pass
        return data

    @cached_property
    def deps_to_install(self) -> set:
        return self.required_deps - self.installed_deps

    def pip_install(self):
        print("=" * 50)
        print("  依赖更新")
        print("=" * 50)

        if not self.InstallDependencies:
            print("InstallDependencies 已禁用，跳过")
            return

        if not self.deps_to_install:
            print("所有依赖已是最新")
            return

        print(f"需要安装的依赖: {self.deps_to_install}")

        print("\n--- Python 版本 ---")
        self.execute(f'"{self.python}" --version')

        # 构建 pip install 参数
        arg = []
        if self.PypiMirror:
            mirror = self.PypiMirror
            arg += ["-i", mirror]
            if "http:" in mirror or not self.SSLVerify:
                arg += ["--trusted-host", urlparse(mirror).hostname]

        arg += ["--disable-pip-version-check"]
        arg_str = " " + " ".join(arg) if arg else ""

        print("\n--- pip install ---")
        self.execute(f'{self.pip} install -r {self.requirements_file}{arg_str}')
