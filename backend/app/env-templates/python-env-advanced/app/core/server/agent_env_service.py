"""
Agent Environment Service - Business logic for agent environment operations.
"""
import json
import logging
import zipfile
import uuid
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from .models import FileNode, FolderSummary, WorkspaceTreeResponse

logger = logging.getLogger(__name__)


class AgentEnvService:
    """
    Handles business logic for agent environment operations.

    Responsibilities:
    - Read/write agent prompt files (WORKFLOW_PROMPT.md, ENTRYPOINT_PROMPT.md)
    - Manage workspace configuration
    - Validate file operations
    """

    def __init__(self, workspace_dir: str):
        """
        Initialize AgentEnvService.

        Args:
            workspace_dir: Path to workspace directory
        """
        self.workspace_dir = Path(workspace_dir)
        self.docs_dir = self.workspace_dir / "docs"
        self.credentials_dir = self.workspace_dir / "credentials"

    def get_agent_prompts(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get current agent prompts from docs files.

        Returns:
            Tuple of (workflow_prompt, entrypoint_prompt)
            Either value can be None if file doesn't exist or is empty
        """
        workflow_prompt = self._read_prompt_file("WORKFLOW_PROMPT.md")
        entrypoint_prompt = self._read_prompt_file("ENTRYPOINT_PROMPT.md")

        return workflow_prompt, entrypoint_prompt

    def update_agent_prompts(
        self,
        workflow_prompt: Optional[str] = None,
        entrypoint_prompt: Optional[str] = None
    ) -> list[str]:
        """
        Update agent prompts in docs files.

        Args:
            workflow_prompt: New content for WORKFLOW_PROMPT.md (None to skip)
            entrypoint_prompt: New content for ENTRYPOINT_PROMPT.md (None to skip)

        Returns:
            List of updated filenames

        Raises:
            IOError: If file write fails
        """
        # Ensure docs directory exists
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []

        if workflow_prompt is not None:
            self._write_prompt_file("WORKFLOW_PROMPT.md", workflow_prompt)
            updated_files.append("WORKFLOW_PROMPT.md")
            logger.info(f"Updated WORKFLOW_PROMPT.md ({len(workflow_prompt)} chars)")

        if entrypoint_prompt is not None:
            self._write_prompt_file("ENTRYPOINT_PROMPT.md", entrypoint_prompt)
            updated_files.append("ENTRYPOINT_PROMPT.md")
            logger.info(f"Updated ENTRYPOINT_PROMPT.md ({len(entrypoint_prompt)} chars)")

        return updated_files

    def _read_prompt_file(self, filename: str) -> Optional[str]:
        """
        Read a prompt file from docs directory.

        Args:
            filename: Name of the file to read

        Returns:
            File content if exists and not empty, None otherwise
        """
        file_path = self.docs_dir / filename

        if not file_path.exists():
            logger.debug(f"{filename} not found at {file_path}")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    logger.info(f"Read {filename} ({len(content)} chars)")
                    return content
                else:
                    logger.debug(f"{filename} is empty")
                    return None
        except Exception as e:
            logger.error(f"Failed to read {filename}: {e}")
            return None

    def _write_prompt_file(self, filename: str, content: str):
        """
        Write content to a prompt file in docs directory.

        Args:
            filename: Name of the file to write
            content: Content to write

        Raises:
            IOError: If write operation fails
        """
        file_path = self.docs_dir / filename

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Wrote {filename} ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Failed to write {filename}: {e}")
            raise IOError(f"Failed to write {filename}: {str(e)}")

    def validate_workspace(self) -> bool:
        """
        Validate that workspace directory exists and is accessible.

        Returns:
            True if workspace is valid, False otherwise
        """
        if not self.workspace_dir.exists():
            logger.error(f"Workspace directory does not exist: {self.workspace_dir}")
            return False

        if not self.workspace_dir.is_dir():
            logger.error(f"Workspace path is not a directory: {self.workspace_dir}")
            return False

        # Check if we can write to workspace
        try:
            test_file = self.workspace_dir / ".workspace_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Workspace is not writable: {e}")
            return False

    def ensure_docs_directory(self):
        """
        Ensure docs directory exists in workspace.

        Creates the directory if it doesn't exist.
        """
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured docs directory exists: {self.docs_dir}")

    def get_workspace_info(self) -> dict:
        """
        Get information about the workspace.

        Returns:
            Dictionary with workspace metadata
        """
        scripts_dir = self.workspace_dir / "scripts"
        files_dir = self.workspace_dir / "files"
        uploads_dir = self.workspace_dir / "uploads"

        return {
            "workspace_dir": str(self.workspace_dir),
            "docs_dir": str(self.docs_dir),
            "has_scripts_dir": scripts_dir.exists(),
            "has_files_dir": files_dir.exists(),
            "has_uploads_dir": uploads_dir.exists(),
            "has_docs_dir": self.docs_dir.exists(),
            "has_workflow_prompt": (self.docs_dir / "WORKFLOW_PROMPT.md").exists(),
            "has_entrypoint_prompt": (self.docs_dir / "ENTRYPOINT_PROMPT.md").exists(),
        }

    def update_credentials(
        self,
        credentials_json: list[dict],
        credentials_readme: str
    ) -> list[str]:
        """
        Update credentials in workspace credentials directory.

        Creates two files:
        - credentials/credentials.json: Full credentials data with actual values
        - credentials/README.md: Redacted documentation for agent prompt

        Args:
            credentials_json: List of credentials with full data
            credentials_readme: Markdown content with redacted credentials

        Returns:
            List of updated filenames

        Raises:
            IOError: If file write fails
        """
        import json

        # Ensure credentials directory exists
        self.credentials_dir.mkdir(parents=True, exist_ok=True)

        updated_files = []

        try:
            # Write credentials.json with full data
            credentials_file = self.credentials_dir / "credentials.json"
            with open(credentials_file, 'w', encoding='utf-8') as f:
                json.dump(credentials_json, f, indent=2)
            updated_files.append("credentials.json")
            logger.info(f"Updated credentials.json ({len(credentials_json)} credentials)")

            # Write README.md with redacted data
            readme_file = self.credentials_dir / "README.md"
            with open(readme_file, 'w', encoding='utf-8') as f:
                f.write(credentials_readme)
            updated_files.append("README.md")
            logger.info(f"Updated credentials/README.md ({len(credentials_readme)} chars)")

            return updated_files

        except Exception as e:
            logger.error(f"Failed to update credentials: {e}")
            raise IOError(f"Failed to update credentials: {str(e)}")

    def get_credentials_readme(self) -> Optional[str]:
        """
        Get credentials README content.

        Returns:
            Content of credentials/README.md if exists and not empty, None otherwise
        """
        readme_file = self.credentials_dir / "README.md"

        if not readme_file.exists():
            logger.debug(f"credentials/README.md not found at {readme_file}")
            return None

        try:
            with open(readme_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    logger.info(f"Read credentials/README.md ({len(content)} chars)")
                    return content
                else:
                    logger.debug("credentials/README.md is empty")
                    return None
        except Exception as e:
            logger.error(f"Failed to read credentials/README.md: {e}")
            return None

    def get_agent_handover_config(self) -> dict:
        """
        Get agent handover configuration from JSON file.

        Returns:
            Dictionary with handovers list and handover_prompt, or empty structure if file doesn't exist
        """
        config_file = self.docs_dir / "agent_handover_config.json"

        if not config_file.exists():
            logger.debug(f"agent_handover_config.json not found at {config_file}")
            return {"handovers": [], "handover_prompt": ""}

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Read agent_handover_config.json ({len(config.get('handovers', []))} handovers)")
                return config
        except Exception as e:
            logger.error(f"Failed to read agent_handover_config.json: {e}")
            return {"handovers": [], "handover_prompt": ""}

    def update_agent_handover_config(
        self,
        handovers: list[dict],
        handover_prompt: str
    ) -> bool:
        """
        Update agent handover configuration in JSON file.

        Creates/updates docs/agent_handover_config.json with:
        - handovers: Array of {id, name, prompt} objects
        - handover_prompt: Prompt text to append to conversation mode system prompt

        Args:
            handovers: List of handover configs with id, name, prompt fields
            handover_prompt: Instructions for handover tool usage

        Returns:
            True if successful, False otherwise

        Raises:
            IOError: If file write fails
        """
        # Ensure docs directory exists
        self.docs_dir.mkdir(parents=True, exist_ok=True)

        config_file = self.docs_dir / "agent_handover_config.json"
        config = {
            "handovers": handovers,
            "handover_prompt": handover_prompt
        }

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Updated agent_handover_config.json ({len(handovers)} handovers)")
            return True
        except Exception as e:
            logger.error(f"Failed to write agent_handover_config.json: {e}")
            raise IOError(f"Failed to write agent_handover_config.json: {str(e)}")

    def validate_workspace_path(self, relative_path: str) -> Path:
        """
        Validate a relative path is safe and within workspace.

        Args:
            relative_path: User-provided path (e.g., "files/data.csv")

        Returns:
            Resolved absolute Path if valid

        Security Checks:
        1. Reject absolute paths (starts with /)
        2. Reject paths with .. components
        3. Resolve to absolute path
        4. Verify resolved path is under workspace_dir
        5. Check for symlinks pointing outside workspace

        Raises:
            ValueError: If path is invalid or unsafe
        """
        # 1. Reject absolute paths
        if relative_path.startswith('/'):
            raise ValueError("Absolute paths not allowed")

        # 2. Reject .. components
        if '..' in Path(relative_path).parts:
            raise ValueError("Parent directory references (..) not allowed")

        # 3. Resolve to absolute path
        full_path = (self.workspace_dir / relative_path).resolve()

        # 4. Verify within workspace boundary
        try:
            full_path.relative_to(self.workspace_dir.resolve())
        except ValueError:
            raise ValueError("Path outside workspace boundary")

        # 5. Check symlinks don't escape workspace
        if full_path.is_symlink():
            link_target = full_path.readlink()
            if link_target.is_absolute():
                resolved_target = link_target.resolve()
            else:
                resolved_target = (full_path.parent / link_target).resolve()

            try:
                resolved_target.relative_to(self.workspace_dir.resolve())
            except ValueError:
                raise ValueError("Symlink points outside workspace")

        return full_path

    def get_workspace_tree(self) -> WorkspaceTreeResponse:
        """
        Build complete workspace tree for files, logs, scripts, docs, uploads folders.

        Returns:
            WorkspaceTreeResponse with full tree structure and summaries

        Raises:
            IOError: If workspace directory doesn't exist or isn't accessible
        """
        if not self.workspace_dir.exists():
            raise IOError(f"Workspace directory does not exist: {self.workspace_dir}")

        if not self.workspace_dir.is_dir():
            raise IOError(f"Workspace path is not a directory: {self.workspace_dir}")

        # Define the 5 main folders to scan
        folders = ["files", "logs", "scripts", "docs", "uploads"]
        tree_nodes = {}
        summaries = {}

        for folder_name in folders:
            folder_path = self.workspace_dir / folder_name

            if not folder_path.exists():
                # Create empty folder node if directory doesn't exist
                logger.warning(f"Folder {folder_name} does not exist, creating empty node")
                tree_nodes[folder_name] = FileNode(
                    name=folder_name,
                    type="folder",
                    path=folder_name,
                    size=0,
                    modified=None,
                    children=[]
                )
                summaries[folder_name] = FolderSummary(fileCount=0, totalSize=0)
            else:
                # Build tree for existing folder
                logger.debug(f"Building tree for {folder_name}")
                node = self._build_tree_recursive(folder_path, self.workspace_dir)
                tree_nodes[folder_name] = node

                # Calculate summary
                summary = self._calculate_folder_summary(node)
                summaries[folder_name] = summary
                logger.info(f"{folder_name}: {summary.fileCount} files, {summary.totalSize} bytes")

        return WorkspaceTreeResponse(
            files=tree_nodes["files"],
            logs=tree_nodes["logs"],
            scripts=tree_nodes["scripts"],
            docs=tree_nodes["docs"],
            uploads=tree_nodes["uploads"],
            summaries=summaries
        )

    def _build_tree_recursive(self, dir_path: Path, relative_to: Path) -> FileNode:
        """
        Recursively build tree structure for a directory.

        Args:
            dir_path: Absolute path to directory
            relative_to: Base path for calculating relative paths

        Returns:
            FileNode with children populated recursively
        """
        # Get relative path
        try:
            rel_path = dir_path.relative_to(relative_to)
            path_str = str(rel_path)
        except ValueError:
            # Shouldn't happen if we're called correctly, but handle gracefully
            path_str = dir_path.name

        # Get directory metadata
        try:
            stat = dir_path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
        except Exception as e:
            logger.warning(f"Failed to get metadata for {dir_path}: {e}")
            modified = None

        # Create folder node
        node = FileNode(
            name=dir_path.name,
            type="folder",
            path=path_str,
            size=None,  # Will be calculated later if needed
            modified=modified,
            children=[]
        )

        # List directory contents
        try:
            items = list(dir_path.iterdir())
        except PermissionError as e:
            logger.warning(f"Permission denied reading {dir_path}: {e}")
            return node
        except Exception as e:
            logger.error(f"Error reading directory {dir_path}: {e}")
            return node

        # Separate files and folders
        files = []
        folders = []

        for item in items:
            # Skip hidden files and __pycache__
            if item.name.startswith('.') or item.name == '__pycache__':
                continue

            if item.is_file():
                try:
                    stat = item.stat()
                    file_node = FileNode(
                        name=item.name,
                        type="file",
                        path=str(item.relative_to(relative_to)),
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        children=None
                    )
                    files.append(file_node)
                except Exception as e:
                    logger.warning(f"Failed to process file {item}: {e}")

            elif item.is_dir():
                # Recursively process subdirectory
                try:
                    folder_node = self._build_tree_recursive(item, relative_to)
                    folders.append(folder_node)
                except Exception as e:
                    logger.warning(f"Failed to process directory {item}: {e}")

        # Sort: folders alphabetically first, then files alphabetically
        folders.sort(key=lambda x: x.name.lower())
        files.sort(key=lambda x: x.name.lower())

        # Combine into children list
        node.children = folders + files

        return node

    def _calculate_folder_summary(self, node: FileNode) -> FolderSummary:
        """
        Calculate fileCount and totalSize for a folder tree.

        Args:
            node: Root FileNode (must be type="folder")

        Returns:
            FolderSummary with counts and sizes
        """
        if node.type != "folder":
            # If it's a file, count it
            return FolderSummary(fileCount=1, totalSize=node.size or 0)

        file_count = 0
        total_size = 0

        # Recursively traverse children
        if node.children:
            for child in node.children:
                if child.type == "file":
                    file_count += 1
                    total_size += child.size or 0
                else:
                    # Recursively process subfolder
                    sub_summary = self._calculate_folder_summary(child)
                    file_count += sub_summary.fileCount
                    total_size += sub_summary.totalSize

        return FolderSummary(fileCount=file_count, totalSize=total_size)

    def create_workspace_zip(self, relative_path: str) -> Path:
        """
        Create a zip archive of a workspace folder or file.

        Args:
            relative_path: Path relative to workspace root (e.g., "files/project1")

        Returns:
            Path to created zip file in /tmp

        Security:
        1. Validate relative_path doesn't escape workspace (no .., absolute paths)
        2. Resolve to absolute path and verify it's under workspace_dir
        3. Check path exists

        Implementation:
        1. Validate and resolve path
        2. Create temporary zip file: /tmp/workspace_{uuid}.zip
        3. If path is file: add single file to zip
        4. If path is folder: recursively add all contents
        5. Return zip file path

        Raises:
            IOError: If path invalid, doesn't exist, or zip creation fails
        """
        # Validate path
        try:
            absolute_path = self.validate_workspace_path(relative_path)
        except ValueError as e:
            raise IOError(f"Invalid path: {e}")

        if not absolute_path.exists():
            raise IOError(f"Path does not exist: {relative_path}")

        # Create temp zip file
        zip_id = str(uuid.uuid4())[:8]
        zip_path = Path(f"/tmp/workspace_{zip_id}.zip")

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                if absolute_path.is_file():
                    # Add single file
                    arcname = absolute_path.name
                    zipf.write(absolute_path, arcname=arcname)
                    logger.debug(f"Added file {arcname} to zip")
                else:
                    # Add folder recursively
                    for item in absolute_path.rglob('*'):
                        if item.is_file():
                            # Skip hidden files and __pycache__
                            if any(part.startswith('.') or part == '__pycache__' for part in item.parts):
                                continue

                            # Calculate relative path within the zip
                            arcname = item.relative_to(absolute_path)
                            zipf.write(item, arcname=str(arcname))

                    logger.debug(f"Added folder {absolute_path.name} to zip")

            logger.info(f"Created zip archive: {zip_path} ({zip_path.stat().st_size} bytes)")
            return zip_path

        except Exception as e:
            # Clean up zip file if creation failed
            if zip_path.exists():
                zip_path.unlink()
            logger.error(f"Failed to create zip archive: {e}")
            raise IOError(f"Failed to create zip archive: {str(e)}")

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for agent-env storage.

        Rules:
        - Remove/replace dangerous characters
        - Preserve extension
        - Limit length to 255 characters
        - Replace spaces with underscores
        """
        import re
        import unicodedata
        import os

        # Normalize unicode
        filename = unicodedata.normalize('NFKD', filename)
        filename = filename.encode('ascii', 'ignore').decode('ascii')

        # Remove path separators and dangerous chars
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', filename)

        # Replace spaces with underscores
        filename = filename.replace(' ', '_')

        # Remove multiple underscores
        filename = re.sub(r'_+', '_', filename)

        # Truncate to 255 chars while preserving extension
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            max_name_len = 255 - len(ext)
            filename = name[:max_name_len] + ext

        # Ensure filename is not empty
        if not filename:
            filename = "file"

        return filename

    @staticmethod
    def resolve_filename_conflict(
        filename: str,
        directory: Path,
        max_attempts: int = 100
    ) -> str:
        """
        Generate unique filename if conflict exists.

        If document.pdf exists, tries:
        - document_1.pdf
        - document_2.pdf
        - ...
        - document_100.pdf

        Raises HTTPException if max_attempts exceeded.
        """
        from fastapi import HTTPException
        import os

        base_path = directory / filename
        if not base_path.exists():
            return filename

        name, ext = os.path.splitext(filename)

        for i in range(1, max_attempts + 1):
            new_filename = f"{name}_{i}{ext}"
            new_path = directory / new_filename
            if not new_path.exists():
                return new_filename

        raise HTTPException(
            status_code=500,
            detail=f"Could not resolve filename conflict for {filename} after {max_attempts} attempts"
        )
