import asyncio
import os
import sys
import time

import psutil

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.utils.astrbot_path import get_astrbot_path

from .zip_updator import ReleaseInfo, RepoZipUpdator


class AstrBotUpdator(RepoZipUpdator):
    """AstrBot 更新器，继承自 RepoZipUpdator 类
    该类用于处理 AstrBot 的更新操作
    功能包括检查更新、下载更新文件、解压缩更新文件等
    """

    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        super().__init__(repo_mirror, verify=verify)
        self.MAIN_PATH = get_astrbot_path()
        self.ASTRBOT_RELEASE_API = "https://api.soulter.top/releases"

    def terminate_child_processes(self) -> None:
        """终止当前进程的所有子进程
        使用 psutil 库获取当前进程的所有子进程，并尝试终止它们
        """
        try:
            parent = psutil.Process(os.getpid())
            children = parent.children(recursive=True)
            logger.info(f"正在终止 {len(children)} 个子进程。")
            for child in children:
                logger.info(f"正在终止子进程 {child.pid}")
                child.terminate()
                try:
                    child.wait(timeout=3)
                except psutil.NoSuchProcess:
                    continue
                except psutil.TimeoutExpired:
                    logger.info(f"子进程 {child.pid} 没有被正常终止, 正在强行杀死。")
                    child.kill()
        except psutil.NoSuchProcess:
            pass

    @staticmethod
    def _is_option_arg(arg: str) -> bool:
        return arg.startswith("-")

    @classmethod
    def _collect_flag_values(cls, argv: list[str], flag: str) -> str | None:
        try:
            idx = argv.index(flag)
        except ValueError:
            return None

        if idx + 1 >= len(argv):
            return None

        value_parts: list[str] = []
        for arg in argv[idx + 1 :]:
            if cls._is_option_arg(arg):
                break
            if arg:
                value_parts.append(arg)

        if not value_parts:
            return None

        return " ".join(value_parts).strip() or None

    @classmethod
    def _resolve_webui_dir_arg(cls, argv: list[str]) -> str | None:
        return cls._collect_flag_values(argv, "--webui-dir")

    def _build_frozen_reboot_args(self) -> list[str]:
        argv = list(sys.argv[1:])
        webui_dir = self._resolve_webui_dir_arg(argv)
        if not webui_dir:
            webui_dir = os.environ.get("ASTRBOT_WEBUI_DIR")

        if webui_dir:
            return ["--webui-dir", webui_dir]
        return []

    @staticmethod
    def _reset_pyinstaller_environment() -> None:
        if not getattr(sys, "frozen", False):
            return
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in list(os.environ.keys()):
            if key.startswith("_PYI_"):
                os.environ.pop(key, None)

    def _build_reboot_argv(self, executable: str) -> list[str]:
        if os.environ.get("ASTRBOT_CLI") == "1":
            args = sys.argv[1:]
            return [executable, "-m", "astrbot.cli.__main__", *args]
        if getattr(sys, "frozen", False):
            args = self._build_frozen_reboot_args()
            return [executable, *args]
        return [executable, *sys.argv]

    @staticmethod
    def _exec_reboot(executable: str, argv: list[str]) -> None:
        if os.name == "nt" and getattr(sys, "frozen", False):
            quoted_executable = f'"{executable}"' if " " in executable else executable
            quoted_args = [f'"{arg}"' if " " in arg else arg for arg in argv[1:]]
            os.execl(executable, quoted_executable, *quoted_args)
            return
        os.execv(executable, argv)

    def _reboot(self, delay: int = 3) -> None:
        """重启当前程序
        在指定的延迟后，终止所有子进程并重新启动程序
        这里只能使用 os.exec* 来重启程序
        """
        time.sleep(delay)
        self.terminate_child_processes()
        executable = sys.executable

        try:
            self._reset_pyinstaller_environment()
            reboot_argv = self._build_reboot_argv(executable)
            self._exec_reboot(executable, reboot_argv)
        except Exception as e:
            logger.error(f"重启失败（{executable}, {e}），请尝试手动重启。")
            raise e

    def is_source_git_install(self) -> bool:
        """当前是否为基于 git 的源码安装。

        是则更新走 ``git pull``（拉取当前分支的远端，例如自建 fork），
        否则回退官方 release zip 下载。
        """
        return os.path.exists(os.path.join(self.MAIN_PATH, ".git"))

    async def _run_git(self, *args: str, timeout: float = 180.0) -> tuple[int, str, str]:
        """在项目目录执行 git 命令，返回 (returncode, stdout, stderr)。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                self.MAIN_PATH,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise Exception("未找到 git 可执行文件，无法以 git 模式更新。") from e
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError) as e:
            proc.kill()
            raise Exception(f"git {' '.join(args)} 执行超时。") from e
        return (
            proc.returncode or 0,
            out_b.decode("utf-8", "replace").strip(),
            err_b.decode("utf-8", "replace").strip(),
        )

    async def _current_branch(self) -> str:
        code, out, _ = await self._run_git(
            "rev-parse", "--abbrev-ref", "HEAD", timeout=15
        )
        return out if code == 0 else ""

    async def _update_via_git(self) -> str:
        """以 git 方式更新：fetch + pull --ff-only（拉取当前分支的远端）。"""
        branch = await self._current_branch()
        logger.info(f"以 git 模式更新 AstrBot Core（分支：{branch or '未知'}）...")
        code, out, err = await self._run_git("fetch", "--prune")
        if code != 0:
            raise Exception(f"git fetch 失败：{err or out}")
        code, out, err = await self._run_git("pull", "--ff-only")
        if code != 0:
            raise Exception(
                "git pull --ff-only 失败（本地可能有未提交改动，或与远端分叉无法快进）："
                f"{err or out}"
            )
        logger.info(f"git 更新完成：{out}")
        return out

    async def _check_update_via_git(self) -> ReleaseInfo | None:
        branch = await self._current_branch()
        code, _, _ = await self._run_git("fetch", "--prune", timeout=60)
        if code != 0:
            return None
        code, out, _ = await self._run_git(
            "rev-list", "--count", "HEAD..@{u}", timeout=15
        )
        if code != 0 or not out.isdigit() or int(out) <= 0:
            return None
        behind = int(out)
        _, head, _ = await self._run_git("rev-parse", "--short", "@{u}", timeout=15)
        _, subject, _ = await self._run_git(
            "log", "-1", "--pretty=%s", "@{u}", timeout=15
        )
        return ReleaseInfo(
            version=f"{branch}@{head}",
            published_at="",
            body=f"git 分支 {branch} 落后远端 {behind} 个提交。最新：{subject}",
        )

    async def check_update(
        self,
        url: str | None,
        current_version: str | None,
        consider_prerelease: bool = True,
    ) -> ReleaseInfo | None:
        """检查更新"""
        if self.is_source_git_install():
            return await self._check_update_via_git()
        return await super().check_update(
            self.ASTRBOT_RELEASE_API,
            VERSION,
            consider_prerelease,
        )

    async def get_releases(self) -> list:
        return await self.fetch_release_info(self.ASTRBOT_RELEASE_API)

    async def update(
        self,
        reboot=False,
        latest=True,
        version=None,
        proxy="",
        progress_callback=None,
    ) -> None:
        if os.environ.get("ASTRBOT_CLI") or os.environ.get("ASTRBOT_LAUNCHER"):
            raise Exception(
                "Error: You are running AstrBot via CLI, please use `pip` or `uv tool upgrade` to update AstrBot."
            )  # 避免版本管理混乱

        # 源码 + git 安装：直接拉取当前分支的远端（例如自建 fork），不下载官方 zip
        if self.is_source_git_install():
            await self._update_via_git()
            if reboot:
                self._reboot()
            return

        update_data = await self.fetch_release_info(self.ASTRBOT_RELEASE_API, latest)
        file_url = None

        if latest:
            latest_version = update_data[0]["tag_name"]
            if self.compare_version(VERSION, latest_version) >= 0:
                raise Exception("当前已经是最新版本。")
            file_url = update_data[0]["zipball_url"]
        elif str(version).startswith("v"):
            # 更新到指定版本
            for data in update_data:
                if data["tag_name"] == version:
                    file_url = data["zipball_url"]
            if not file_url:
                raise Exception(f"未找到版本号为 {version} 的更新文件。")
        else:
            if len(str(version)) != 40:
                raise Exception("commit hash 长度不正确，应为 40")
            file_url = f"https://github.com/AstrBotDevs/AstrBot/archive/{version}.zip"
        logger.info(f"准备更新至指定版本的 AstrBot Core: {version}")

        if proxy:
            proxy = proxy.removesuffix("/")
            file_url = f"{proxy}/{file_url}"

        try:
            await self._download_file(
                file_url,
                "temp.zip",
                progress_callback=progress_callback,
            )
            logger.info("下载 AstrBot Core 更新文件完成，正在执行解压...")
            self.unzip_file("temp.zip", self.MAIN_PATH)
        except BaseException as e:
            raise e

        if reboot:
            self._reboot()
