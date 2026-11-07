"""Check Git updates for AstrBot source installations."""

import pytest

from astrbot.core.updater import AstrBotUpdater
from astrbot.core.zip_updater import ReleaseInfo


@pytest.fixture
def updater(tmp_path):
    up = AstrBotUpdater()
    (tmp_path / ".git").mkdir()
    up._main_path = str(tmp_path)
    return up


def test_is_source_git_install(updater):
    assert updater.is_source_git_install() is True


def test_is_source_git_install_false(tmp_path):
    up = AstrBotUpdater()
    up._main_path = str(tmp_path)
    assert up.is_source_git_install() is False


@pytest.mark.asyncio
async def test_update_uses_git_pull_and_skips_release_downloads(updater, monkeypatch):
    calls = []

    async def fake_run_git(*args, timeout=180.0):
        calls.append(args)
        if args[:3] == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, "Dev", ""
        return 0, "Already up to date.", ""

    async def must_not_call(*args, **kwargs):
        raise AssertionError("Git mode must not download a release archive.")

    monkeypatch.setattr(updater, "_run_git", fake_run_git)
    monkeypatch.setattr(updater, "_fetch_release_info", must_not_call)
    monkeypatch.setattr(updater, "_download_core_package", must_not_call)

    await updater.update()

    assert ("fetch", "--prune") in calls
    assert ("pull", "--ff-only") in calls


@pytest.mark.asyncio
async def test_update_git_pull_not_fastforward_raises(updater, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:3] == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, "Dev", ""
        if args[0] == "fetch":
            return 0, "", ""
        if args[0] == "pull":
            return 1, "", "Not possible to fast-forward, aborting."
        return 0, "", ""

    monkeypatch.setattr(updater, "_run_git", fake_run_git)
    with pytest.raises(Exception, match="ff-only"):
        await updater.update()


@pytest.mark.asyncio
async def test_check_update_reports_behind(updater, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:3] == ("rev-parse", "--abbrev-ref", "HEAD"):
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

    monkeypatch.setattr(updater, "_run_git", fake_run_git)
    info = await updater.check_update()
    assert isinstance(info, ReleaseInfo)
    assert "3 commits behind" in info.body


@pytest.mark.asyncio
async def test_check_update_uptodate_returns_none(updater, monkeypatch):
    async def fake_run_git(*args, timeout=180.0):
        if args[:3] == ("rev-parse", "--abbrev-ref", "HEAD"):
            return 0, "Dev", ""
        if args[0] == "fetch":
            return 0, "", ""
        if args[0] == "rev-list":
            return 0, "0", ""
        return 0, "", ""

    monkeypatch.setattr(updater, "_run_git", fake_run_git)
    assert await updater.check_update() is None
