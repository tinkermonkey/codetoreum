"""Repository URL parsing utilities for multi-project management.

Provides utilities for extracting repository information from URLs
in both SSH and HTTPS formats.
"""


def extract_repo_name(repo_url: str) -> str:
    """Extract repository name from URL.

    Handles both SSH and HTTPS repository URLs, extracting the repository
    name (final path component) without the .git suffix if present.

    Supports:
    - SSH format: git@github.com:org/repo.git → repo
    - HTTPS format: https://github.com/org/repo.git → repo
    - HTTPS (no .git): https://github.com/org/repo → repo
    - Nested paths: https://example.com/org/sub/repo.git → repo

    Args:
        repo_url: Repository URL in SSH or HTTPS format

    Returns:
        str: Repository name (final path component without .git)

    Raises:
        ValueError: If repo_url is empty, None, or contains only whitespace

    Example:
        >>> extract_repo_name("git@github.com:acme/api-service.git")
        'api-service'
        >>> extract_repo_name("https://github.com/acme/api-service.git")
        'api-service'
        >>> extract_repo_name("https://github.com/acme/api-service")
        'api-service'
        >>> extract_repo_name("https://vcs.example.com/orgs/team/repo.git")
        'repo'
    """
    if not repo_url or not repo_url.strip():
        raise ValueError("repo_url cannot be empty, None, or whitespace-only")

    # Remove trailing .git if present
    url = repo_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # Handle SSH format: git@github.com:org/repo -> repo
    if "@" in url and ":" in url:
        # Extract the part after the colon
        after_colon = url.split(":")[-1]
        # Get the last path component
        return after_colon.split("/")[-1]

    # Handle HTTPS format: https://github.com/org/repo -> repo
    # Get the last path component
    return url.split("/")[-1]
