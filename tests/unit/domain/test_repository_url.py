"""Unit tests for repository URL parsing utilities."""

import pytest
from codetoreum.domain.repository_url import extract_repo_name


class TestExtractRepoName:
    """Test suite for extract_repo_name utility function."""

    def test_ssh_url_with_git_extension(self):
        """Extract repo name from SSH URL with .git extension."""
        url = "git@github.com:acme/api-service.git"
        assert extract_repo_name(url) == "api-service"

    def test_ssh_url_without_git_extension(self):
        """Extract repo name from SSH URL without .git extension."""
        url = "git@github.com:acme/api-service"
        assert extract_repo_name(url) == "api-service"

    def test_https_url_with_git_extension(self):
        """Extract repo name from HTTPS URL with .git extension."""
        url = "https://github.com/acme/api-service.git"
        assert extract_repo_name(url) == "api-service"

    def test_https_url_without_git_extension(self):
        """Extract repo name from HTTPS URL without .git extension."""
        url = "https://github.com/acme/api-service"
        assert extract_repo_name(url) == "api-service"

    def test_https_url_with_trailing_slash(self):
        """Extract repo name from HTTPS URL with trailing slash."""
        url = "https://github.com/acme/api-service.git/"
        assert extract_repo_name(url) == "api-service"

    def test_nested_path_ssh_url(self):
        """Extract repo name from SSH URL with nested organization structure."""
        url = "git@vcs.example.com:orgs/team/documentation_robotics.git"
        assert extract_repo_name(url) == "documentation_robotics"

    def test_nested_path_https_url(self):
        """Extract repo name from HTTPS URL with nested organization structure."""
        url = "https://vcs.example.com/orgs/team/documentation_robotics.git"
        assert extract_repo_name(url) == "documentation_robotics"

    def test_ssh_with_multiple_colons(self):
        """Extract repo name from SSH URL with port specification."""
        url = "git@example.com:22/org/repo.git"
        assert extract_repo_name(url) == "repo"

    def test_single_word_repo_name(self):
        """Extract single-word repository name."""
        url = "https://github.com/org/docrobotics.git"
        assert extract_repo_name(url) == "docrobotics"

    def test_repo_name_with_hyphens(self):
        """Extract repository name containing hyphens."""
        url = "git@github.com:org/api-service-v2.git"
        assert extract_repo_name(url) == "api-service-v2"

    def test_repo_name_with_underscores(self):
        """Extract repository name containing underscores."""
        url = "https://github.com/org/api_service_v2.git"
        assert extract_repo_name(url) == "api_service_v2"

    def test_repo_name_with_dots(self):
        """Extract repository name containing dots."""
        url = "https://github.com/org/service.api.git"
        assert extract_repo_name(url) == "service.api"

    def test_bitbucket_https_url(self):
        """Extract repo name from Bitbucket HTTPS URL."""
        url = "https://bitbucket.org/team/repository.git"
        assert extract_repo_name(url) == "repository"

    def test_bitbucket_ssh_url(self):
        """Extract repo name from Bitbucket SSH URL."""
        url = "git@bitbucket.org:team/repository.git"
        assert extract_repo_name(url) == "repository"

    def test_gitlab_https_url(self):
        """Extract repo name from GitLab HTTPS URL."""
        url = "https://gitlab.com/group/subgroup/project.git"
        assert extract_repo_name(url) == "project"

    def test_empty_string_raises_error(self):
        """Raise ValueError when given empty string."""
        with pytest.raises(ValueError, match="repo_url cannot be empty, None, or whitespace-only"):
            extract_repo_name("")

    def test_none_raises_error(self):
        """Raise ValueError when given None."""
        with pytest.raises(ValueError, match="repo_url cannot be empty, None, or whitespace-only"):
            extract_repo_name(None)  # type: ignore

    def test_whitespace_only_string(self):
        """Raise ValueError when given whitespace-only string."""
        with pytest.raises(ValueError, match="repo_url cannot be empty, None, or whitespace-only"):
            extract_repo_name("   ")

    def test_custom_git_server_https(self):
        """Extract repo name from custom git server HTTPS URL."""
        url = "https://git.company.internal/projects/core/backend.git"
        assert extract_repo_name(url) == "backend"

    def test_custom_git_server_ssh(self):
        """Extract repo name from custom git server SSH URL."""
        url = "git@git.company.internal:projects/core/backend.git"
        assert extract_repo_name(url) == "backend"

    def test_url_with_query_parameters(self):
        """Handle HTTPS URL with query parameters."""
        # Note: Query parameters should normally not be in a git URL,
        # but this test documents the exact current behavior.
        url = "https://github.com/org/repo.git?ref=main"
        # Query parameters are treated as part of the repo name
        result = extract_repo_name(url)
        assert result == "repo.git?ref=main"

    def test_preserves_repo_name_case(self):
        """Preserve case of repository name."""
        url = "https://github.com/org/MyAwesomeRepo.git"
        assert extract_repo_name(url) == "MyAwesomeRepo"

    def test_numeric_repo_names(self):
        """Extract numeric repository names."""
        url = "https://github.com/org/12345.git"
        assert extract_repo_name(url) == "12345"

    def test_deeply_nested_path(self):
        """Extract repo name from deeply nested path structure."""
        url = "https://vcs.company.com/orgs/teams/projects/subprojects/service.git"
        assert extract_repo_name(url) == "service"

    def test_alternative_git_protocols(self):
        """Extract repo name from git:// protocol URL."""
        url = "git://github.com/org/repo.git"
        assert extract_repo_name(url) == "repo"

    def test_bare_repo_directory(self):
        """Extract repo name from bare repository directory pattern."""
        url = "https://git.example.com/repos/my-app.git"
        assert extract_repo_name(url) == "my-app"
