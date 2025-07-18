import pytest
import sys
import os
from unittest.mock import Mock, patch

class TestAiderMCPServer:
    
    @pytest.fixture(autouse=True)
    def setup_module(self):
        """Setup the aider_mcp_server module for testing."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        with patch('atexit.register'), \
             patch('logging.basicConfig'):
            
            # Import the main server module directly
            import importlib.util
            spec = importlib.util.spec_from_file_location("aider_mcp_server", 
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aider_mcp_server.py"))
            self.aider_mcp_server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.aider_mcp_server)
    
    def test_aider_start_already_running(self):
        """Test starting Aider when already running."""
        mock_process_manager = Mock()
        mock_process_manager.is_running.return_value = True
        
        with patch.object(self.aider_mcp_server, 'process_manager', mock_process_manager):
            result = self.aider_mcp_server.aider_start()
            
            assert "already running" in result
            mock_process_manager.start_aider.assert_not_called()
    
    def test_aider_send_message(self):
        """Test sending message to Aider."""
        with patch.object(self.aider_mcp_server, '_interact_with_aider') as mock_interact:
            mock_interact.return_value = "Aider response"
            
            result = self.aider_mcp_server.aider_send_message("test prompt")
            
            mock_interact.assert_called_once_with("test prompt", filter_startup_noise=False)
            assert result == "Aider response"
    
    def test_aider_get_status(self):
        """Test getting Aider status."""
        mock_process_manager = Mock()
        mock_process_manager.get_status_info.return_value = {
            'process_id': 12345,
            'is_running': True,
            'exit_code': None,
            'output_queue_size': 5,
            'reader_thread_alive': True
        }
        
        with patch.object(self.aider_mcp_server, 'process_manager', mock_process_manager):
            result = self.aider_mcp_server.aider_get_status()
            
            assert "Process ID: 12345" in result
            assert "Process alive: True" in result
    
    def test_aider_quick_start_unknown_workflow(self):
        """Test quick start with unknown workflow."""
        result = self.aider_mcp_server.aider_quick_start("unknown_workflow")
        
        assert "Unknown workflow" in result
        assert "debug" in result  # Should list available workflows
    
    def test_aider_configure_not_running(self):
        """Test configuration when Aider not running."""
        mock_process_manager = Mock()
        mock_process_manager.is_running.return_value = False
        
        with patch.object(self.aider_mcp_server, 'process_manager', mock_process_manager):
            result = self.aider_mcp_server.aider_configure("architect", "true")
            
            assert "Aider is not running" in result
