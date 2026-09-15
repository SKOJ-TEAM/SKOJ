PYTHON_MEMORY_LIMIT_KB = 1024 * 1024


def execution_time_limit(language_key, configured_limit):
    """Apply the Python 3 per-test-case ceiling after selecting configured limits."""
    return min(configured_limit, 10.0) if language_key == 'PY3' else configured_limit


def execution_memory_limit(language_key, configured_limit):
    """Cap the selected Python 3 allowance at 1024 MiB."""
    if language_key != 'PY3':
        return configured_limit
    # Zero means unlimited to the sandbox; still enforce the Python ceiling.
    configured_limit = configured_limit or PYTHON_MEMORY_LIMIT_KB
    return min(configured_limit, PYTHON_MEMORY_LIMIT_KB)
