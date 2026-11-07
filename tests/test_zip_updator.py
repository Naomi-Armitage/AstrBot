from astrbot.core.repository import GitHubRepository


def test_parse_github_url_supports_branch_names_with_slashes():
    repository = GitHubRepository.parse(
        "https://github.com/example/my_plugin/tree/codex/custom-update-branch"
    )

    assert repository.owner == "example"
    assert repository.name == "my_plugin"
    assert repository.branch == "codex/custom-update-branch"
