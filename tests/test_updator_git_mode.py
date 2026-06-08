"""验证源码 + git 安装下，更新器走 git pull 而非下载官方 zip（方案 A）。"""

import pytest

from astrbot.core.updator import AstrBotUpdator
from astrbot.core.zip_updator import ReleaseInfo


@pytest.fixture
def updator(tmp_path):
    up = AstrBotUpdator()
    # 构造一个含 .git 的目录，使 is_source_git_install() 确定性为 True
    (tmp_path / ".git").mkdir()
    up.MAIN_PATH = str(tmp_path)
    return up


def test_is_source_git_install(updator):
    assert updator.is_source_git_install() is True


def test_is_source_git_install_false(tmp_path):
    up = AstrBotUpdator()
    up.MAIN_PATH = str(tmp_path)  # 无 .git
    assert up.is_source_git_install() is False


@pytest.mark.asyncio
async def test_update_uses_git_pull_and_skips_zip(updator, monkeypatch):
    calls = []

    async def fake_run_git(*args, timeout=180.0):
        calls.append(args)
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, "Dev", ""
        return 0, "Already up to date.", ""

    async def must_not_call(*a, **k):
        raise AssertionError("git 模式下不应下载官方 zip / 拉取官方 release")

    monkeypatch.setattr(updator, "_run_git", fake_run_git)
    monkeypatch.setattr(updator, "_download_file", must_not_call)
    monkeypatch.setattr(updator, "fetch_release_info", must_not_call)

    await updator.update(latest=True, reboot=False)

    assert ("fetch", "--prune") in calls
    assert ("pull", "--ff-only") in calls


@pytest.mark.asyncio
async def test_update_git_pull_not_fastforward_raises(updator, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, "Dev", ""
        if args[0] == "fetch":
            return 0, "", ""
        if args[0] == "pull":
            return 1, "", "Not possible to fast-forward, aborting."
        return 0, "", ""

    monkeypatch.setattr(updator, "_run_git", fake_run_git)
    with pytest.raises(Exception, match="ff-only"):
        await updator.update(reboot=False)


@pytest.mark.asyncio
async def test_check_update_reports_behind(updator, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, "Dev", ""
        if args[0] == "fetch":
            return 0, "", ""
        if args[0] == "rev-list":
            return 0, "3", ""
        if args[0] == "rev-parse":
            return 0, "abc1234", ""
        if args[0] == "log":
            return 0, "feat: something", ""
        return 0, "", ""

    monkeypatch.setattr(updator, "_run_git", fake_run_git)
    info = await updator.check_update(None, None)
    assert isinstance(info, ReleaseInfo)
    assert "落后远端 3" in info.body


@pytest.mark.asyncio
async def test_check_update_uptodate_returns_none(updator, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return 0, "Dev", ""
        if args[0] == "fetch":
            return 0, "", ""
        if args[0] == "rev-list":
            return 0, "0", ""
        return 0, "", ""

    monkeypatch.setattr(updator, "_run_git", fake_run_git)
    assert await updator.check_update(None, None) is None
