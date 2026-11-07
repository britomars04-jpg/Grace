"""Memory manager for session persistence and cross-session memory."""

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("memory_manager")


class MemoryManager:
    """Manages persistent session memory stored in a markdown file."""

    def __init__(self, storage_path: str = "session_memory.md"):
        self.storage_path = Path(storage_path)
        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        """Create the memory file with a header if it doesn't exist."""
        if not self.storage_path.exists():
            self.storage_path.write_text(
                "# Voice Assistant Session History\n", encoding="utf-8"
            )
            logger.info(f"Created memory file: {self.storage_path}")

    def get_memory_summary(self) -> str:
        """Read and return the entire contents of the memory file."""
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            if not content.strip():
                return "No prior session notes found."
            return content
        except FileNotFoundError:
            return "No prior session notes found."

    def append_session(self, summary_text: str) -> None:
        """Append a new session summary to the memory file."""
        timestamp = datetime.now().isoformat()
        entry = f"\n---\n### Session Date: {timestamp}\n**Summary:**\n{summary_text}\n"
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"Appended session summary to {self.storage_path}")

    def open_in_notepad(self) -> None:
        """Open the memory file in Notepad (Windows) non-blocking."""
        if sys.platform == "win32":
            try:
                # Use os.startfile on Windows - non-blocking
                os.startfile(str(self.storage_path))
                logger.info(f"Opened {self.storage_path} in Notepad")
            except Exception as e:
                logger.error(f"Failed to open in Notepad: {e}")
                # Fallback to subprocess
                subprocess.Popen(["notepad.exe", str(self.storage_path)])
        else:
            # For non-Windows, try common text editors
            try:
                subprocess.Popen(["notepad", str(self.storage_path)])
            except Exception:
                try:
                    subprocess.Popen(["gedit", str(self.storage_path)])
                except Exception as e:
                    logger.error(f"Failed to open text editor: {e}")

    async def generate_summary_from_chat_ctx(self, chat_ctx, llm_instance=None) -> str:
        """Generate a concise summary from the chat context.

        Args:
            chat_ctx: The LiveKit ChatContext object
            llm_instance: Optional LLM instance for summarization

        Returns:
            A 3-sentence summary of the conversation
        """
        # Extract user and assistant text turns
        turns = []
        try:
            for item in chat_ctx.items:
                role = getattr(item, "role", None)
                if role in ("user", "assistant"):
                    # Try multiple ways to get text content
                    text = ""
                    if hasattr(item, "text_content") and item.text_content:
                        text = item.text_content
                    elif hasattr(item, "content") and item.content:
                        content = item.content
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            # Handle list content (multimodal)
                            for part in content:
                                if hasattr(part, "text") and part.text:
                                    text += part.text
                                elif isinstance(part, str):
                                    text += part

                    if text:
                        turns.append(f"{role}: {text}")
        except Exception as e:
            logger.error(f"Error extracting turns from chat context: {e}")
            return f"Error generating summary: {e}"

        if not turns:
            return "No conversation recorded."

        # If we have an LLM instance, use it for summarization
        if llm_instance:
            try:
                from livekit.agents import llm as livekit_llm

                summary_ctx = livekit_llm.ChatContext()
                summary_ctx.add_message(
                    role="system",
                    content="Summarize this conversation in exactly 3 sentences. Focus on: 1) key facts mentioned, 2) user preferences, and 3) any unresolved tasks or questions. Be concise.",
                )
                summary_ctx.add_message(
                    role="user",
                    content="\n".join(turns[-10:]),  # Last 10 turns for context
                )

                response = await llm_instance.chat(chat_ctx=summary_ctx).collect()
                if response.text:
                    return response.text.strip()
            except Exception as e:
                logger.warning(f"LLM summarization failed, using fallback: {e}")

        # Fallback: simple extraction of key information
        user_turns = [t for t in turns if t.startswith("user:")]
        assistant_turns = [t for t in turns if t.startswith("assistant:")]

        summary_parts = []
        if user_turns:
            summary_parts.append(
                f"User engaged in conversation with {len(user_turns)} exchanges."
            )
        if assistant_turns:
            summary_parts.append(
                f"Assistant provided {len(assistant_turns)} responses."
            )

        # Add last user message if available
        if user_turns:
            last_user = user_turns[-1][:100]
            summary_parts.append(f"Latest user query: {last_user}...")

        return " ".join(summary_parts) if summary_parts else "Conversation completed."
