import pytest
from unittest.mock import Mock, patch
from aider_mcp_server.process_manager import AiderProcessManager

class TestAiderProcessManager:
    
    def test_init(self):
        """Test ProcessManager initialization."""
        manager = AiderProcessManager()
        assert manager._process is None
        assert manager._output_queue is None
        assert manager._reader_thread is None
    
    def test_is_running_no_process(self, process_manager):
        """Test is_running when no process exists."""
        assert not process_manager.is_running()
    
    def test_is_running_with_process(self, process_manager, mock_process):
        """Test is_running with active process."""
        process_manager._process = mock_process
        assert process_manager.is_running()
    
    def test_send_command_no_process(self, process_manager):
        """Test sending command when no process exists."""
        with pytest.raises(ConnectionError, match="Aider process is not running"):
            process_manager.send_command("test command")
    
    def test_send_command_success(self, process_manager, mock_process):
        """Test successful command sending."""
        process_manager._process = mock_process
        
        process_manager.send_command("test command")
        
        mock_process.stdin.write.assert_called_once_with("test command\n")
        mock_process.stdin.flush.assert_called_once()
    
    def test_get_status_info_no_process(self, process_manager):
        """Test status info when no process exists."""
        status = process_manager.get_status_info()
        
        assert status["process_id"] is None
        assert status["is_running"] is False
        assert status["exit_code"] is None
        assert status["output_queue_size"] == 0
        assert status["reader_thread_alive"] is False
    
    def test_stop_aider_no_process(self, process_manager):
        """Test stopping when no process exists."""
        result = process_manager.stop_aider()
        assert result == "Aider is not running."
