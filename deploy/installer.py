"""
更新器主入口
运行: python -m deploy.installer
"""
import os
import sys

# 确保项目根在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from deploy.git import GitManager
from deploy.pip import PipManager
from deploy.config import ExecutionError


class Installer(GitManager, PipManager):
    def install(self):
        print()
        print("=" * 50)
        print("  物华弥新抽卡分析器 - 更新器")
        print("=" * 50)

        try:
            self.git_install()
            self.pip_install()
            print()
            print("  更新完成！正在启动...")
            print("=" * 50)
        except ExecutionError:
            print()
            print("  更新失败，请检查网络连接")
            print("  或编辑 config/deploy.yaml 调整配置")
            sys.exit(1)


if __name__ == "__main__":
    Installer().install()
