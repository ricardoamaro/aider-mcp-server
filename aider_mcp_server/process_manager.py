import os
import sys
import subprocess
import threading
import queue
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union

logger = logging.getLogger(__name__)

class AiderProcessManager:
    def __init__(self):
        self._process: Union[subprocess.Popen, None] = None
        self._output_queue: Union[queue.Queue, None] = None
        self._reader_thread: Union[threading.Thread, None] = None
        self._last_command_cache = {"command": None, "count": 0, "timestamp": 0}

    def _enqueue_output(self, pipe, q):
        """Reads output from the aider process pipe and puts it into a queue, also logging it."""
        try:
            for line in iter(pipe.readline, ''):
                stripped_line = line.strip()
                if not stripped_line: # Skip logging purely empty lines
                    continue
                logger.debug(f"Aider STDOUT/ERR: {stripped_line}")
                q.put(line)
        except ValueError as e:
            logger.warning(f"Error reading from Aider pipe (might be closed): {e}")
        finally:
            pipe.close()
            logger.info("Aider output pipe reader thread exited.")

    def start_aider(self, files: List[str] = None, model: str = None, message: str = None) -> None:
        """Starts the Aider subprocess."""
        if self._process and self._process.poll() is None:
            logger.info("Aider is already running. Skipping start.")
            return

        command = [sys.executable, "-m", "aider.main"]
        if files:
            command.extend(files)
        if model:
            command.extend(["--model", model])
        if message:
            command.extend(["--message", message])

        static_flags = [
            "--no-pretty",
            "--no-stream",
            "--auto-test",
            "--architect",
            "--auto-accept-architect",
            "--no-show-model-warnings",
            "--no-suggest-shell-commands",
            "--yes-always",
            "--subtree-only",
            "--watch-files",
        ]
        command.extend(static_flags)

        logger.info(f"Starting aider with command: {' '.join(command)}")

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Redirect stderr to stdout
            text=True,
            bufsize=1, # Line-buffered
            cwd=os.getcwd()
        )

        output_q = queue.Queue()
        reader_thread = threading.Thread(target=self._enqueue_output, args=(process.stdout, output_q))
        reader_thread.daemon = True
        reader_thread.start()

        self._process = process
        self._output_queue = output_q
        self._reader_thread = reader_thread
        logger.info("Aider process started and reader thread launched.")

    def send_command(self, command: str):
        """Sends a command to the Aider process's stdin."""
        # Circuit breaker for repeated commands
        current_time = time.time()
        if (self._last_command_cache["command"] == command and
            current_time - self._last_command_cache["timestamp"] < 30):
            self._last_command_cache["count"] += 1
            if self._last_command_cache["count"] > 3:
                logger.warning(f"Detected repeated command '{command}' - possible loop")
                raise ConnectionError("[LOOP DETECTED] Same command repeated multiple times. Please try a different approach.")
        else:
            self._last_command_cache["command"] = command
            self._last_command_cache["count"] = 1
            self._last_command_cache["timestamp"] = current_time

        if not self.is_running():
            return_code_info = f" (exit code: {self._process.returncode})" if self._process else ""
            logger.error(f"Aider process is not running or has terminated unexpectedly{return_code_info}.")
            self.stop_aider(graceful=False) # Attempt to clean up state
            raise ConnectionError(f"Aider process is not running. Please call 'aider_start' first, or it has crashed{return_code_info}.")

        logger.debug(f"Sending command to Aider: '{command}' (length: {len(command)} chars)")
        command_start_time = time.time()

        try:
            self._process.stdin.write(command + '\n')
            self._process.stdin.flush()
            logger.debug(f"Command sent successfully in {time.time() - command_start_time:.3f}s")
        except BrokenPipeError:
            logger.error(f"Broken pipe when trying to write to Aider's stdin. Aider process likely crashed.")
            self.stop_aider(graceful=False)
            raise ConnectionError("Failed to send command to Aider: Broken pipe. Aider process likely crashed.")
        except Exception as e:
            logger.error(f"Error sending command to Aider stdin: {e}")
            self.stop_aider(graceful=False)
            raise ConnectionError(f"Error sending command to Aider: {e}")

    def get_output_queue(self) -> queue.Queue:
        """Returns the output queue."""
        return self._output_queue

    def get_process(self) -> Union[subprocess.Popen, None]:
        """Returns the subprocess.Popen object."""
        return self._process

    def is_running(self) -> bool:
        """Checks if the Aider process is currently running."""
        return self._process is not None and self._process.poll() is None

    def get_status_info(self) -> Dict[str, Any]:
        """Returns detailed status information about the Aider process."""
        status_info = {
            "process_id": self._process.pid if self._process else None,
            "is_running": self.is_running(),
            "exit_code": self._process.returncode if self._process and self._process.poll() is not None else None,
            "output_queue_size": self._output_queue.qsize() if self._output_queue else 0,
            "reader_thread_alive": self._reader_thread.is_alive() if self._reader_thread else False,
        }
        return status_info

    def stop_aider(self, graceful: bool = True) -> str:
        """
        Stops the Aider subprocess and cleans up associated resources.
        Attempts a graceful exit first, then a forceful termination if needed.
        """
        if not self._process or self._process.poll() is not None:
            return "Aider is not running."

        logger.info("Attempting to stop Aider process...")
        try:
            if graceful and self._process.stdin:
                try:
                    self._process.stdin.write("/exit\n")
                    self._process.stdin.flush()
                    logger.debug("Sent /exit command to Aider.")
                except BrokenPipeError:
                    logger.warning("Broken pipe when trying to send /exit command. Aider might already be dead.")
                    pass

            # Wait for graceful exit. If it doesn't exit, it'll timeout.
            self._process.wait(timeout=10)
            logger.info("Aider process exited gracefully.")
        except subprocess.TimeoutExpired:
            logger.warning("Aider did not exit gracefully within 10s, terminating forcefully.")
            self._process.terminate() # Send SIGTERM
            try:
                self._process.wait(timeout=5) # Give it a moment to terminate
            except subprocess.TimeoutExpired:
                logger.error("Aider process did not terminate after SIGTERM, killing it (SIGKILL).")
                self._process.kill() # Send SIGKILL
        except Exception as e:
            logger.error(f"Error during Aider stop: {e}")
        finally:
            self._process = None
            self._output_queue = None
            self._reader_thread = None
            logger.info("Aider process resources cleaned up.")
        return "Aider process stopped."

    def force_stop_aider(self) -> str:
        """Emergency stop for runaway Aider processes. Forces immediate termination."""
        if not self._process:
            return "No Aider process to stop."

        logger.warning("Emergency stop initiated - killing Aider process immediately")
        try:
            self._process.kill()  # Immediate SIGKILL
            self._process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
        finally:
            self._process = None
            self._output_queue = None
            self._reader_thread = None
            logger.info("Emergency stop completed. Aider process terminated.")
        return "Emergency stop completed. Aider process terminated."
