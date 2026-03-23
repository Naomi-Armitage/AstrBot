from astrbot.core.zip_updator import RepoZipUpdator


def test_parse_github_url_supports_branch_names_with_slashes():
    updator = RepoZipUpdator()

    author, repo, branch = updator.parse_github_url(
        "https://github.com/example/my_plugin/tree/codex/custom-update-branch"
    )

    assert author == "example"
    assert repo == "my_plugin"
    assert branch == "codex/custom-update-branch"
