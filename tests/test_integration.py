import pytest
import os
import sys
from unittest.mock import patch, Mock

class TestIntegration:
    """Minimal integration tests."""
    
    def test_error_handling_chain(self):
        """Test error handling across components."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        with patch('atexit.register'), \
             patch('logging.basicConfig'):
            
            # Import the main server module directly
            import importlib.util
            spec = importlib.util.spec_from_file_location("aider_mcp_server", 
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aider_mcp_server.py"))
            aider_mcp_server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(aider_mcp_server)
            
            # Test sending message without starting Aider
            with pytest.raises(ConnectionError):
                aider_mcp_server._interact_with_aider("test command")
    
    def test_status_reporting_integration(self):
        """Test status reporting across components."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        with patch('atexit.register'), \
             patch('logging.basicConfig'):
            
            # Import the main server module directly
            import importlib.util
            spec = importlib.util.spec_from_file_location("aider_mcp_server", 
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aider_mcp_server.py"))
            aider_mcp_server = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(aider_mcp_server)
            
            # Get status when no process is running
            status = aider_mcp_server.aider_get_status()
            
            assert "Process ID: None" in status
            assert "Process alive: False" in status
