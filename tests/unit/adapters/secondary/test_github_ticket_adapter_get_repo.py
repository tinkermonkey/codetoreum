"""Unit tests for GitHubTicketAdapter._get_repo project_id resolution.

Covers the multi-project repo resolution threaded through get_work_item /
get_comments / get_related_items: a registered project_id resolves to its repo;
an *unknown explicit* project_id fails loudly (rather than silently resolving to
the wrong/only repo); and the no-project back-compat fallbacks still work.
"""

import pytest

from codetoreum.adapters.secondary import GitHubConfig, GitHubTicketAdapter
from codetoreum.ports.exceptions import ConfigurationError


def _adapter(repository: str = "", projects: dict | None = None) -> GitHubTicketAdapter:
    adapter = GitHubTicketAdapter(GitHubConfig(token="t", organization="org", repository=repository))
    for project_id, repo in (projects or {}).items():
        adapter.register_project_repo(project_id, repo)
    return adapter


def test_resolves_registered_project_id():
    adapter = _adapter(projects={"proj-a": "repo-a", "proj-b": "repo-b"})
    assert adapter._get_repo("proj-a") == "repo-a"
    assert adapter._get_repo("proj-b") == "repo-b"


def test_unknown_explicit_project_id_raises_when_projects_registered():
    adapter = _adapter(projects={"proj-a": "repo-a", "proj-b": "repo-b"})
    with pytest.raises(ConfigurationError):
        adapter._get_repo("does-not-exist")


def test_none_project_id_falls_back_to_single_registered_repo():
    adapter = _adapter(projects={"only": "repo-only"})
    assert adapter._get_repo(None) == "repo-only"


def test_multiple_registered_without_project_id_raises():
    adapter = _adapter(projects={"proj-a": "repo-a", "proj-b": "repo-b"})
    with pytest.raises(ConfigurationError):
        adapter._get_repo(None)


def test_no_projects_registered_falls_back_to_config_repository():
    # Back-compat path used by tests: nothing registered, so even an explicit
    # project_id falls through to config.repository rather than raising.
    adapter = _adapter(repository="config-repo")
    assert adapter._get_repo(None) == "config-repo"
    assert adapter._get_repo("anything") == "config-repo"
