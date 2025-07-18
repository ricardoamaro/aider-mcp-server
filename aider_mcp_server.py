# [[file:../research-mcp.org::*MCP AIDER Coding Assistant Service][MCP AIDER Coding Assistant Service:1]]
import os
import sys
import subprocess
import threading
import queue
import re
import atexit
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Any, Tuple, Union
import logging
import time

# Import the new modules
from aider_mcp_server.process_manager import AiderProcessManager
from aider_mcp_server.response_handler import AiderResponseHandler

# Configure logging for the module
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Server Setup ---
mcp = FastMCP("Aider Coding Assistant Service", tool_timeout=300)

# --- Initialize Managers ---
process_manager = AiderProcessManager()
response_handler = AiderResponseHandler()

# --- Helper function to interact with Aider (send command and get response) ---
def _interact_with_aider(command: str, filter_startup_noise: bool = False) -> str:
    """
    Sends a command to the Aider process and reads the response using the managers.
    Handles ConnectionError by stopping Aider.
    """
    try:
        # Send the command via the process manager (handles circuit breaker)
        process_manager.send_command(command)

        # Read the response via the response handler
        # Pass the process object to allow the response handler to check process status
        response = response_handler.read_response(process_manager.get_output_queue(), process_manager.get_process(), filter_startup_noise)
        return response
    except ConnectionError as e:
        logger.error(f"Connection error during Aider interaction: {e}")
        process_manager.stop_aider(graceful=False) # Ensure cleanup
        raise

@mcp.tool()
def aider_start(files: List[str] = None, model: str = None, message: str = None) -> str:
    """
    Starts the Aider subprocess and initializes a coding session.
    This is the first tool you must call to begin interacting with Aider.
    The response will be Aider's initial prompt, indicating it's ready for instructions.

    :param files: A list of file paths to load into the Aider session immediately.
                  Aider will read and include these files in its context.
                  Example: `files=["src/main.py", "tests/test_foo.py"]`
    :param model: The specific LLM model Aider should use (e.g., 'gpt-4o', 'gpt-3.5-turbo').
                  If not provided, Aider will use its default model.
                  Example: `model="gpt-4o"`
    :param message: An initial message or prompt to start the session with.
                    This can be a high-level goal or an immediate coding task.
                    Example: `message="Refactor the 'UserService' class to use dependency injection."`
    :return: The initial output from Aider, typically its prompt ready for input.
    """
    if process_manager.is_running():
        return "Aider is already running. Call 'aider_stop' to restart or continue with 'aider_send_message'."

    try:
        process_manager.start_aider(files, model, message)
        # Wait for the initial prompt to ensure aider is ready
        initial_response = _interact_with_aider("", filter_startup_noise=True) # Filter noise for initial startup
        logger.info("Aider initial prompt received. Aider is ready.")
        return initial_response
    except ConnectionError as e:
        logger.error(f"Failed to get initial Aider prompt: {e}")
        process_manager.stop_aider(graceful=False) # Ensure cleanup if start fails
        raise

@mcp.tool()
def aider_send_message(prompt: str) -> str:
    """
    Sends a message or natural language prompt to the active Aider agent.
    This is your primary way to provide instructions, describe coding tasks,
    ask questions, or guide Aider's behavior.

    To "start coding," first use `aider_start` and then send your coding instructions
    via this tool.

    To engage in an "architect mode" or high-level discussion, simply formulate your
    `prompt` with architectural questions or directives. Aider responds to your
    natural language input, so frame your prompt accordingly.
    Examples:
    - "Refactor the 'authentication' module to use OAuth2 for better security."
    - "Design a new database schema for user profiles, including fields for name, email, and preferences."
    - "Review the current project structure and suggest improvements for scalability."

    :param prompt: The text message or instruction to send to Aider.
    :return: Aider's response, including any code suggestions, explanations, or questions.
    """
    return _interact_with_aider(prompt, filter_startup_noise=False) # Do not filter for messages; capture all relevant output

@mcp.tool()
def aider_add_files(paths: List[str]) -> str:
    """
    Adds one or more files to the Aider chat context using the Aider `/add` command.
    Aider will read these files and consider them for future code modifications.

    :param paths: A list of file paths to add.
                  Example: `paths=["new_feature.py", "config.ini"]`
    :return: Aider's confirmation or relevant output.
    """
    command = f"/add {' '.join(paths)}" # Aider will respond with "Added X to the chat." which is useful.
    return _interact_with_aider(command)

@mcp.tool()
def aider_drop_files(paths: List[str]) -> str:
    """
    Removes one or more files from the Aider chat context using the Aider `/drop` command.
    Aider will no longer consider these files for modifications.

    :param paths: A list of file paths to drop.
                  Example: `paths=["old_script.py"]`
    :return: Aider's confirmation or relevant output.
    """
    command = f"/drop {' '.join(paths)}" # Aider will respond with "Dropped X from the chat." which is useful.
    return _interact_with_aider(command)

@mcp.tool()
def aider_run_command(command: str) -> str:
    """
    Runs a specific Aider internal slash command (e.g., 'test', 'diff', 'commit', 'fix').
    Do NOT include the leading slash (e.g., use "test" not "/test").
    These commands control Aider's internal operations or provide specific functionalities.

    :param command: The Aider slash command to execute (without the leading slash).
                    Examples: "test -v", "diff", "commit", "exit"
    :return: The output from Aider after executing the command.
    """
    return _interact_with_aider(f"/{command}", filter_startup_noise=False) # Keep all output for commands, as it's typically direct results.

@mcp.tool()
def aider_list_files() -> str:
    """
    Lists the files currently included in the Aider chat context via the `/files` command.
    This helps you confirm which files Aider is aware of for coding tasks.

    :return: A list of files managed by Aider in the current session.
    """
    return _interact_with_aider("/files", filter_startup_noise=False) # Keep all output, as it's the list of files.

@mcp.tool()
def aider_get_status() -> str:
    """
    Get the current status and health information of the Aider process.
    This includes process state, memory usage, and connection health.

    :return: Detailed status information about the Aider process.
    """
    status_dict = process_manager.get_status_info()
    status_info_lines = []
    status_info_lines.append(f"Process ID: {status_dict['process_id']}")
    status_info_lines.append(f"Process alive: {status_dict['is_running']}")
    if status_dict['exit_code'] is not None:
        status_info_lines.append(f"Exit code: {status_dict['exit_code']}")
    status_info_lines.append(f"Output queue size: {status_dict['output_queue_size']}")
    status_info_lines.append(f"Reader thread alive: {status_dict['reader_thread_alive']}")

    return "\n".join(status_info_lines)

@mcp.tool()
def aider_get_debug_info() -> str:
    """
    Get comprehensive debug information including recent output,
    process state, and configuration details.

    :return: Debug information for troubleshooting Aider issues.
    """
    debug_info = []
    debug_info.append("=== AIDER DEBUG INFORMATION ===")
    debug_info.append(f"Current working directory: {os.getcwd()}")
    debug_info.append(f"Python executable: {sys.executable}")

    # Process status
    status_dict = process_manager.get_status_info()
    debug_info.append(f"Process ID: {status_dict['process_id']}")
    debug_info.append(f"Process running: {status_dict['is_running']}")
    if status_dict['exit_code'] is not None:
        debug_info.append(f"Exit code: {status_dict['exit_code']}")
    else:
        debug_info.append("Process: Not started")

    # Queue information (can still peek from here as process_manager gives reference)
    output_q = process_manager.get_output_queue()
    if output_q:
        debug_info.append(f"Output queue size: {output_q.qsize()}")

        temp_items = []
        try:
            while not output_q.empty() and len(temp_items) < 5:
                item = output_q.get_nowait()
                temp_items.append(item)

            if temp_items:
                debug_info.append("Recent queue items (up to 5):")
                for i, item in enumerate(temp_items):
                    debug_info.append(f"  {i+1}: {item.strip()}")

                for item in reversed(temp_items):
                    output_q.put(item)
        except queue.Empty:
            pass

    return "\n".join(debug_info)

@mcp.tool()
def aider_test_connection() -> str:
    """
    Test the connection to Aider by sending a simple command and measuring response time.

    :return: Connection test results including response time.
    """
    if not process_manager.is_running():
        return "Connection test failed: Aider process is not running"

    start_time = time.time()
    try:
        response = _interact_with_aider("/help", filter_startup_noise=False)
        end_time = time.time()
        response_time = end_time - start_time

        return f"Connection test successful!\nResponse time: {response_time:.2f} seconds\nResponse length: {len(response)} characters"
    except Exception as e:
        end_time = time.time()
        response_time = end_time - start_time
        return f"Connection test failed after {response_time:.2f} seconds: {str(e)}"

@mcp.tool()
def aider_set_log_level(level: str = "INFO") -> str:
    """
    Set the logging level for the Aider MCP server.

    :param level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    :return: Confirmation of log level change.
    """
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    level = level.upper()

    if level not in valid_levels:
        return f"Invalid log level. Valid levels: {', '.join(valid_levels)}"

    # Set level for the current module's logger
    logger.setLevel(getattr(logging, level))
    # Set level for the imported managers' loggers
    logging.getLogger('AILab.mcpcli.aider_mcp_server.process_manager').setLevel(getattr(logging, level))
    logging.getLogger('AILab.mcpcli.aider_mcp_server.response_handler').setLevel(getattr(logging, level))
    # Also update the root logger level if needed (for global logging configuration)
    logging.getLogger().setLevel(getattr(logging, level))

    return f"Log level set to {level}"

@mcp.tool()
def aider_emergency_stop() -> str:
    """
    Emergency stop for runaway Aider processes. Forces immediate termination.
    Use this if Aider appears to be in an endless loop or unresponsive.

    :return: Confirmation of emergency stop.
    """
    return process_manager.force_stop_aider()

@mcp.tool()
def aider_stop() -> str:
    """
    Stops the Aider subprocess and cleans up associated resources.
    It attempts a graceful exit first, then a forceful termination if needed.
    You should call this when your Aider session is complete.

    :return: A confirmation message that Aider has stopped.
    """
    return process_manager.stop_aider()

@mcp.tool()
def aider_quick_start(workflow: str, target_files: List[str] = None) -> str:
    """
    Quick start with predefined workflows for common tasks.

    :param workflow: Workflow type ('debug', 'refactor', 'feature', 'test', 'review')
    :param target_files: Specific files to work with
    :return: Workflow setup status
    """
    workflows = {
        "debug": {
            "message": "Help me debug issues in the codebase. Start by analyzing the code for potential problems.",
            "config": {"auto_test": "true", "lint": "true"}
        },
        "refactor": {
            "message": "Help me refactor this code to improve structure, readability, and maintainability.",
            "config": {"architect": "true", "auto_commits": "false"}
        },
        "feature": {
            "message": "Help me implement a new feature. Let's start by understanding the requirements.",
            "config": {"auto_commits": "true", "auto_test": "true"}
        },
        "test": {
            "message": "Help me write comprehensive tests for this codebase.",
            "config": {"auto_test": "true", "test_cmd": "python -m pytest -v"}
        },
        "review": {
            "message": "Please review this code and suggest improvements for quality, security, and performance.",
            "config": {"architect": "true"}
        }
    }

    if workflow not in workflows:
        return f"Unknown workflow. Available: {', '.join(workflows.keys())}"

    workflow_config = workflows[workflow]

    try:
        # Start Aider with workflow-specific settings
        result = aider_start(
            files=target_files,
            message=workflow_config["message"]
        )

        # Apply workflow-specific configuration
        config_results = []
        for setting, value in workflow_config["config"].items():
            try:
                config_result = aider_configure(setting, value)
                config_results.append(f"✅ {setting}: {config_result}")
            except Exception as e:
                config_results.append(f"❌ {setting}: {str(e)}")

        config_summary = "\n".join(config_results)

        return f"Workflow '{workflow}' started.\n{result}\n\nConfiguration applied:\n{config_summary}"

    except Exception as e:
        logger.error(f"Failed to start workflow '{workflow}': {e}")
        return f"❌ Failed to start workflow '{workflow}': {str(e)}"

@mcp.tool()
def aider_configure(setting: str, value: str = None) -> str:
    """
    Configure Aider settings during runtime using Aider's slash commands.

    :param setting: Setting to configure ('model', 'architect', 'auto_commits', 'auto_test', 'lint', 'pretty')
    :param value: Value to set ('true'/'false' for boolean settings, model name for 'model')
    :return: Configuration result
    """
    if not process_manager.is_running():
        return "❌ Error: Aider is not running. Start Aider first with aider_start()"

    try:
        # Map settings to Aider slash commands
        if setting == "model":
            command = f"/model {value}" if value else "/model"
        elif setting == "architect":
            command = "/architect" if value != "false" else "/diff"
        elif setting == "auto_commits":
            command = "/auto-commits" if value == "true" else "/no-auto-commits"
        elif setting == "auto_test":
            command = "/auto-test" if value == "true" else "/no-auto-test"
        elif setting == "lint":
            command = "/lint" if value == "true" else "/no-lint"
        elif setting == "pretty":
            command = "/pretty" if value == "true" else "/no-pretty"
        elif setting == "test_cmd":
            command = f"/test-cmd {value}" if value else "/test-cmd"
        else:
            available = "model, architect, auto_commits, auto_test, lint, pretty, test_cmd"
            return f"❌ Unknown setting '{setting}'. Available: {available}"

        logger.info(f"Applying configuration: {command}")
        result = _interact_with_aider(command)
        
        return f"✅ Configuration '{setting}' updated successfully.\nAider response: {result}"

    except Exception as e:
        logger.error(f"Error configuring Aider setting '{setting}': {e}")
        return f"❌ Error configuring Aider: {str(e)}"

# Ensure cleanup happens when the server process exits
atexit.register(process_manager.stop_aider)

if __name__ == "__main__":
    current_working_dir = os.getcwd()

    logger.info(f"Starting Aider MCP Server...")
    logger.info(f"Initial Working Directory: {current_working_dir}")
    logger.info(f"Python executable: {sys.executable}")

    try:
        logger.info(f"Aider module location: {subprocess.check_output([sys.executable, '-c', 'import aider; print(aider.__file__)'], text=True).strip()}")
    except Exception as e:
        logger.warning(f"Could not determine Aider module location: {e}")

    logger.info("Aider will use its default LLM model unless specified in 'aider_start' tool call.")

    logger.info("\n--- Aider MCP Server Usage Guide ---")
    logger.info("🚀 **Quick Start with Workflows**: Use `aider_quick_start(workflow='feature', target_files=['src/app.py'])` for common tasks.")
    logger.info("   Available workflows: 'debug', 'refactor', 'feature', 'test', 'review'")
    logger.info("1. **Initialize Aider**: Call `aider_start()` first. You can optionally specify initial files, a model, and a starting message.")
    logger.info("   Example: `aider_start(files=['src/app.py'], model='gpt-4o', message='Help me implement a login feature.')`")
    logger.info("2. **Send Instructions**: Use `aider_send_message(prompt='...')` to provide coding tasks, architectural guidance, or ask questions.")
    logger.info("   Aider will respond to natural language prompts, acting as a coding assistant or a virtual architect based on your input.")
    logger.info("   Example (Coding): `aider_send_message(prompt='Implement the `User` class with `name` and `email` properties.')`")
    logger.info("   Example (Architectural): `aider_send_message(prompt='Propose a scalable microservices architecture for an e-commerce platform.')`")
    logger.info("3. **Manage Files**: Use `aider_add_files()` and `aider_drop_files()` to control which files Aider has in its context.")
    logger.info("4. **Run Aider Commands**: Use `aider_run_command()` for Aider's internal slash commands (e.g., 'test -v', 'diff', 'commit').")
    logger.info("5. **Configure Settings**: Use `aider_configure(setting, value)` to adjust Aider's behavior during runtime.")
    logger.info("6. **Debug & Monitor**: Use `aider_get_status()`, `aider_get_debug_info()`, `aider_test_connection()` for troubleshooting.")
    logger.info("7. **Stop Aider**: Call `aider_stop()` to end the Aider session and clean up resources when you are done.")
    logger.info("\n--- Debug Tools Available ---")
    logger.info("- `aider_get_status()`: Get current process status")
    logger.info("- `aider_get_debug_info()`: Get comprehensive debug information")
    logger.info("- `aider_test_connection()`: Test connection and response time")
    logger.info("- `aider_set_log_level(level)`: Change logging verbosity (DEBUG, INFO, WARNING, ERROR)")
    logger.info("- `aider_emergency_stop()`: Force immediate termination of runaway processes")
    logger.info("\n------------------------------------")

    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        process_manager.stop_aider()
    except Exception as e:
        logger.error(f"MCP server error: {e}")
        process_manager.stop_aider()
        raise
# MCP AIDER Coding Assistant Service:1 ends here
