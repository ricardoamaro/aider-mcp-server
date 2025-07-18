import queue
import re
import time
import logging
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)

AIDER_PROMPT_REGEX = re.compile(r'^(>|\w+>)\s*$')

AIDER_NOISE_PATTERNS = [
    re.compile(r"Model: .* with diff edit format, prompt cache,"),
    re.compile(r"infinite output"),
    re.compile(r"Note: in-chat filenames are always relative to the git working dir, not the"),
    re.compile(r"current working dir\."),
    re.compile(r"Cur working dir: .*"),
    re.compile(r"Git working dir: .*"),
]

class AiderResponseHandler:
    def __init__(self):
        pass # No state needed for this handler

    def read_response(self, output_q: queue.Queue, process, filter_startup_noise: bool = False) -> str:
        """
        Reads output from the Aider process queue until the AIDER_PROMPT is detected.
        :param output_q: The queue containing Aider's stdout/stderr.
        :param process: The subprocess.Popen object to check its status during reading.
        :param filter_startup_noise: If True, filters out common Aider startup messages.
        :return: The aggregated and optionally filtered response string.
        """
        response_lines = []
        start_time = time.time()
        line_count = 0
        MAX_RESPONSE_LINES = 1000
        line_read_timeout = 5 # seconds to wait for a single line from Aider
        overall_response_timeout = 240 # Increased to allow more time for Aider to return its prompt

        while True:
            try:
                line = output_q.get(timeout=line_read_timeout)
                stripped_line = line.strip()
                response_lines.append(line)
                line_count += 1

                if line_count > MAX_RESPONSE_LINES:
                    logger.warning(f"Response exceeded maximum lines ({MAX_RESPONSE_LINES}), truncating")
                    response_lines.append(f"\n[RESPONSE TRUNCATED - EXCEEDED {MAX_RESPONSE_LINES} LINES]\n")
                    break

                if line_count % 10 == 0:
                    logger.debug(f"Received {line_count} lines from Aider so far...")

                if AIDER_PROMPT_REGEX.match(stripped_line):
                    logger.debug(f"Detected potential Aider prompt: '{stripped_line}'")
                    try:
                        peek_line = output_q.get(timeout=2.0)
                        response_lines.append(peek_line)
                        logger.debug("Found additional output after prompt, continuing...")
                    except queue.Empty:
                        logger.debug(f"Confirmed Aider prompt: '{stripped_line}' - response complete")
                        break

            except queue.Empty:
                if process and process.poll() is not None:
                    logger.error(f"Aider process terminated unexpectedly with exit code {process.returncode if process else 'N/A'} while waiting for response.")
                    return "".join(response_lines) + "\n[AIDER CRASHED UNEXPECTEDLY (during prompt wait)]"

                elapsed_time = time.time() - start_time
                if elapsed_time > overall_response_timeout:
                    logger.warning(f"Aider response timeout ({overall_response_timeout}s) reached. No prompt or output received for a long time.")
                    logger.warning(f"Received {line_count} lines before timeout")
                    return "".join(response_lines) + "\n[AIDER TIMEOUT (No prompt within allowed time)]"

                logger.debug(f"Queue empty for {line_read_timeout}s, waiting for Aider output... (elapsed: {elapsed_time:.1f}s, lines: {line_count})")

        total_time = time.time() - start_time
        logger.info(f"Aider response completed: {line_count} lines in {total_time:.2f}s")

        final_response_lines = []
        filtered_lines = 0
        for line in response_lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            if filter_startup_noise:
                is_noise = False
                for pattern in AIDER_NOISE_PATTERNS:
                    if pattern.match(stripped_line):
                        is_noise = True
                        filtered_lines += 1
                        break
                if not is_noise:
                    final_response_lines.append(line)
            else:
                final_response_lines.append(line)

        if filter_startup_noise and filtered_lines > 0:
            logger.debug(f"Filtered out {filtered_lines} noise lines from response")

        return "".join(final_response_lines).strip()
