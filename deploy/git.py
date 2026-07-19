"""
Git 更新逻辑
"""
import os

from deploy.config import DeployConfig


class GitManager(DeployConfig):
    @cached_property
    def git(self) -> str:
        exe = self.filepath("GitExecutable")
        if os.path.exists(exe):
            return exe
        print(f"[WARN] Git not found: {exe}, fallback to system git")
        return "git"

    def git_install(self):
        print("=" * 50)
        print("  Git 更新")
        print("=" * 50)

        if not self.AutoUpdate:
            print("AutoUpdate 已禁用，跳过")
            return

        repo = self.Repository
        branch = self.Branch
        proxy = self.GitProxy
        ssl_verify = self.SSLVerify

        # git init
        print("\n--- Git Init ---")
        if not self.execute(f'"{self.git}" init', allow_failure=True):
            for f in ["./.git/config", "./.git/index", "./.git/HEAD"]:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
            self.execute(f'"{self.git}" init')

        # proxy
        print("\n--- Git Proxy ---")
        if proxy:
            self.execute(f'"{self.git}" config --local http.proxy {proxy}')
            self.execute(f'"{self.git}" config --local https.proxy {proxy}')
        else:
            self.execute(
                f'"{self.git}" config --local --unset http.proxy', allow_failure=True
            )
            self.execute(
                f'"{self.git}" config --local --unset https.proxy', allow_failure=True
            )

        if ssl_verify:
            self.execute(
                f'"{self.git}" config --local http.sslVerify true', allow_failure=True
            )
        else:
            self.execute(
                f'"{self.git}" config --local http.sslVerify false', allow_failure=True
            )

        # remote
        print("\n--- Git Remote ---")
        if not self.execute(
            f'"{self.git}" remote set-url origin {repo}', allow_failure=True
        ):
            self.execute(f'"{self.git}" remote add origin {repo}')

        # fetch
        print("\n--- Git Fetch ---")
        self.execute(f'"{self.git}" fetch origin {branch}')

        # pull
        print("\n--- Git Pull ---")
        for lock in [
            "./.git/index.lock",
            "./.git/HEAD.lock",
            f"./.git/refs/heads/{branch}.lock",
        ]:
            if os.path.exists(lock):
                print(f"  清理锁文件: {lock}")
                os.remove(lock)

        self.execute(f'"{self.git}" reset --hard origin/{branch}')
        self.execute(f'"{self.git}" pull --ff-only origin {branch}')

        # version
        print("\n--- 当前版本 ---")
        self.execute(f'"{self.git}" --no-pager log --no-merges -1')
