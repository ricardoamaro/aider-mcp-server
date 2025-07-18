import pytest
import tempfile
import os
from unittest.mock import Mock
from aider_mcp_server.process_manager import AiderProcessManager
from aider_mcp_server.response_handler import AiderResponseHandler

@pytest.fixture
def mock_process():
    """Create a mock subprocess.Popen object."""
    mock = Mock()
    mock.poll.return_value = None  # Process is running
    mock.pid = 12345
    mock.returncode = None
    mock.stdin = Mock()
    mock.stdout = Mock()
    return mock

@pytest.fixture
def process_manager():
    """Create a fresh AiderProcessManager instance."""
    return AiderProcessManager()

@pytest.fixture
def response_handler():
    """Create a fresh AiderResponseHandler instance."""
    return AiderResponseHandler()
