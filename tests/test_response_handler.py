import pytest
import queue
from unittest.mock import Mock
from aider_mcp_server.response_handler import AiderResponseHandler, AIDER_PROMPT_REGEX

class TestAiderResponseHandler:
    
    def test_init(self):
        """Test ResponseHandler initialization."""
        handler = AiderResponseHandler()
        assert handler is not None
    
    def test_prompt_regex_matches(self):
        """Test Aider prompt regex patterns."""
        # Test valid prompts
        assert AIDER_PROMPT_REGEX.match("> ")
        assert AIDER_PROMPT_REGEX.match("main> ")
        
        # Test invalid patterns
        assert not AIDER_PROMPT_REGEX.match("not a prompt")
        assert not AIDER_PROMPT_REGEX.match(">> invalid")
    
    def test_read_response_simple(self, response_handler):
        """Test reading a simple response with prompt."""
        output_q = queue.Queue()
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process running
        
        # Add response lines ending with prompt
        output_q.put("Response line 1\n")
        output_q.put("> \n")  # Aider prompt
        
        response = response_handler.read_response(output_q, mock_process)
        
        assert "Response line 1" in response
        assert response.strip().endswith(">")
    
    def test_read_response_process_terminated(self, response_handler):
        """Test response reading when process terminates unexpectedly."""
        output_q = queue.Queue()
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Process terminated
        mock_process.returncode = 1
        
        output_q.put("Partial response\n")
        
        response = response_handler.read_response(output_q, mock_process)
        
        assert "Partial response" in response
        assert "AIDER CRASHED UNEXPECTEDLY" in response
