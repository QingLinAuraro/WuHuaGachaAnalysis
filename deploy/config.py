"""
部署配置加载
"""
import copy
import os
import sys

from deploy.utils import poor_yaml_read, poor_yaml_write, cached_property, DEPLOY_CONFIG, DEPLOY_TEMPLATE


class ExecutionError(Exception):
    pass


class ConfigModel:
    # Git
    Repository: str = "https://github.com/QingLinAuraro/WuHuaGachaAnalysis"
    Branch: str = "master"
    GitExecutable: str = "./toolkit/Git/mingw64/bin/git.exe"
    GitProxy: str = None
    SSLVerify: bool = True
    AutoUpdate: bool = True

    # Python
    PythonExecutable: str = "./toolkit/python.exe"
    PypiMirror: str = None
    InstallDependencies: bool = True
    RequirementsFile: str = "requirements.txt"

    # ADB
    AdbExecutable: str = "./toolkit/adb/adb.exe"


class DeployConfig(ConfigModel):
    def __init__(self, file: str = DEPLOY_CONFIG):
        self.file = file
        self.config = {}
        self.config_template = {}
        self.root_filepath = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        ).replace("\\", "/")
        self.read()

    def read(self):
        self.config = poor_yaml_read(DEPLOY_TEMPLATE)
        self.config_template = copy.deepcopy(self.config)
        origin = poor_yaml_read(self.file)
        self.config.update(origin)

        for key, value in self.config.items():
            if hasattr(self, key):
                super().__setattr__(key, value)

        if self.config != origin:
            self.write()

    def write(self):
        poor_yaml_write(self.config, self.file)

    def filepath(self, key: str) -> str:
        return (
            os.path.abspath(os.path.join(self.root_filepath, self.config[key]))
            .replace("\\", "/")
        )

    def execute(self, command: str, allow_failure: bool = False, output: bool = True):
        command = command.replace("\\", "/").replace('"', '"')
        if not output:
            command = command + " >nul 2>nul"
        print(f"[EXEC] {command}")
        error_code = os.system(command)
        if error_code:
            if allow_failure:
                print(f"  [allowed failure] code={error_code}")
                return False
            else:
                print(f"  [failure] code={error_code}")
                raise ExecutionError(f"Command failed: {command}")
        else:
            print(f"  [success]")
            return True
