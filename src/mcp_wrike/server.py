"""MCP server for Wrike project management."""

import asyncio
import re

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .auth import get_access_token
from .client import WrikeClient

# Initialize MCP server
server = Server("mcp-wrike")

# Cache for user lookup (id -> name)
_user_cache: dict[str, str] = {}


async def _get_user_name(client: WrikeClient, user_id: str) -> str:
    """Get user display name from ID, with caching."""
    if user_id in _user_cache:
        return _user_cache[user_id]

    try:
        contacts = await client.get_contacts()
        for c in contacts:
            name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
            _user_cache[c["id"]] = name or c.get("email", c["id"])
        return _user_cache.get(user_id, user_id)
    except Exception:
        return user_id


def _format_task(task, include_description: bool = True) -> str:
    """Format task for display."""
    status_display = task.custom_status_name or task.status
    lines = [
        f"**{task.title}**",
        f"- ID: `{task.id}`",
        f"- Status: {status_display}",
    ]

    if task.importance:
        lines.append(f"- Importance: {task.importance}")

    if task.dates:
        if task.dates.get("start"):
            lines.append(f"- Start: {task.dates['start']}")
        if task.dates.get("due"):
            lines.append(f"- Due: {task.dates['due']}")

    if task.created_date:
        lines.append(f"- Created: {task.created_date.strftime('%Y-%m-%d %H:%M')}")

    if task.updated_date:
        lines.append(f"- Updated: {task.updated_date.strftime('%Y-%m-%d %H:%M')}")

    if task.completed_date:
        lines.append(f"- Completed: {task.completed_date.strftime('%Y-%m-%d %H:%M')}")

    if task.parent_ids:
        lines.append(
            f"- Parent folders: {', '.join(f'`{pid}`' for pid in task.parent_ids)}"
        )

    if task.super_task_ids:
        lines.append(
            f"- Parent tasks: {', '.join(f'`{sid}`' for sid in task.super_task_ids)}"
        )

    if task.responsible_ids:
        lines.append(
            f"- Assigned: {', '.join(f'`{rid}`' for rid in task.responsible_ids)}"
        )

    if task.custom_status_id:
        lines.append(f"- Custom status ID: `{task.custom_status_id}`")

    if task.custom_fields:
        cf_parts = []
        for cf in task.custom_fields:
            cf_parts.append(f"`{cf.get('id')}` = {cf.get('value', '')}")
        lines.append(f"- Custom fields: {', '.join(cf_parts)}")

    if task.permalink:
        lines.append(f"- Link: {task.permalink}")

    if include_description and task.description:
        # Strip HTML tags for cleaner output
        clean_desc = re.sub(r"<[^>]+>", "", task.description)
        clean_desc = clean_desc.replace("&nbsp;", " ").strip()
        if clean_desc:
            lines.append(f"\n**Description:**\n{clean_desc}")

    return "\n".join(lines)


def _format_comment(comment, author_name: str = "") -> str:
    """Format comment for display."""
    date_str = (
        comment.created_date.strftime("%Y-%m-%d %H:%M")
        if comment.created_date
        else "Unknown"
    )
    author = author_name or comment.author_id

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", comment.text)
    text = text.replace("&nbsp;", " ").strip()

    return f"**{author}** ({date_str}):\n{text}"


def _format_project(project) -> str:
    """Format project for display."""
    status_display = project.custom_status_name or "No status"
    lines = [
        f"**{project.title}**",
        f"- ID: `{project.id}`",
        f"- Status: {status_display}",
    ]

    if project.owner_ids:
        lines.append(f"- Owners: {', '.join(f'`{oid}`' for oid in project.owner_ids)}")

    if project.created_date:
        lines.append(f"- Created: {project.created_date.strftime('%Y-%m-%d %H:%M')}")

    if project.updated_date:
        lines.append(f"- Updated: {project.updated_date.strftime('%Y-%m-%d %H:%M')}")

    if project.child_ids:
        lines.append(f"- Child folders: {len(project.child_ids)}")

    if project.permalink:
        lines.append(f"- Link: {project.permalink}")

    if project.description:
        clean_desc = re.sub(r"<[^>]+>", "", project.description)
        clean_desc = clean_desc.replace("&nbsp;", " ").strip()
        if clean_desc:
            lines.append(f"\n**Description:**\n{clean_desc}")

    return "\n".join(lines)


def _format_attachment(attachment) -> str:
    """Format attachment for display."""
    date_str = (
        attachment.created_date.strftime("%Y-%m-%d")
        if attachment.created_date
        else "Unknown"
    )
    size_str = f"{attachment.size:,} bytes" if attachment.size else "Unknown size"

    lines = [
        f"- **{attachment.name}**",
        f"  - ID: `{attachment.id}`",
        f"  - Size: {size_str}",
        f"  - Type: {attachment.content_type or 'Unknown'}",
        f"  - Date: {date_str}",
    ]

    if attachment.url:
        lines.append(f"  - URL: {attachment.url}")

    return "\n".join(lines)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="search_tasks",
            description="Search for Wrike tasks by title or status",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Search by title (partial match)",
                    },
                    "status": {
                        "type": "string",
                        "description": (
                            "Filter by status: Active, Completed,"
                            " Deferred, Cancelled"
                        ),
                        "enum": ["Active", "Completed", "Deferred", "Cancelled"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="get_task",
            description="Get detailed information about a specific Wrike task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_task_comments",
            description="Get comments/notes for a Wrike task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum comments to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_task_attachments",
            description="Get attachments for a Wrike task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum attachments to return (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="get_task_full",
            description=(
                "Get complete task details including description,"
                " comments, and attachments"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="list_folders",
            description="List Wrike folders/projects. Use parent_folder_id to list children of a specific folder (e.g., projects under ACv2 Pipeline). Deleted/recycled folders are hidden by default — use include_deleted=true to see them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_folder_id": {
                        "type": "string",
                        "description": "Parent folder ID to list children of. Without this, lists top-level folders.",
                    },
                    "include_deleted": {
                        "type": "boolean",
                        "description": "Include recycle bin folders (default: false)",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum folders to return (default: 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="create_task",
            description="Create a new Wrike task in a folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "string",
                        "description": "The Wrike folder ID to create the task in",
                    },
                    "title": {
                        "type": "string",
                        "description": "Task title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Task description (HTML allowed)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Task status",
                        "enum": ["Active", "Completed", "Deferred", "Cancelled"],
                    },
                    "responsible_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of contact IDs to assign as responsibles",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format",
                    },
                    "importance": {
                        "type": "string",
                        "description": "Task importance",
                        "enum": ["High", "Normal", "Low"],
                    },
                    "custom_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["id", "value"],
                        },
                        "description": "Custom field values as [{id, value}] pairs",
                    },
                    "custom_status": {
                        "type": "string",
                        "description": (
                            "Custom workflow status ID" " (overrides generic status)"
                        ),
                    },
                    "custom_item_type_id": {
                        "type": "string",
                        "description": (
                            "Custom item type ID (e.g., Engineering"
                            " Project, Spike, Bug Report)"
                        ),
                    },
                },
                "required": ["folder_id", "title"],
            },
        ),
        Tool(
            name="update_task",
            description="Update an existing Wrike task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID to update",
                    },
                    "title": {
                        "type": "string",
                        "description": "New task title",
                    },
                    "description": {
                        "type": "string",
                        "description": "New task description (HTML allowed)",
                    },
                    "status": {
                        "type": "string",
                        "description": "New task status",
                        "enum": ["Active", "Completed", "Deferred", "Cancelled"],
                    },
                    "add_responsibles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Contact IDs to add as responsibles",
                    },
                    "remove_responsibles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Contact IDs to remove from responsibles",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format",
                    },
                    "importance": {
                        "type": "string",
                        "description": "Task importance",
                        "enum": ["High", "Normal", "Low"],
                    },
                    "completed_date": {
                        "type": "string",
                        "description": "Completion date override in YYYY-MM-DD format",
                    },
                    "custom_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["id", "value"],
                        },
                        "description": "Custom field values as [{id, value}] pairs",
                    },
                    "custom_status": {
                        "type": "string",
                        "description": (
                            "Custom workflow status ID" " (overrides generic status)"
                        ),
                    },
                    "add_super_tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Task IDs to add as parent tasks"
                            " (makes this task a subtask)"
                        ),
                    },
                    "remove_super_tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Task IDs to remove as parent tasks",
                    },
                    "custom_item_type_id": {
                        "type": "string",
                        "description": (
                            "Custom item type ID (e.g., Engineering"
                            " Project, Spike, Bug Report)"
                        ),
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="delete_task",
            description="Delete a Wrike task permanently",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID to delete",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="create_folder",
            description="Create a new Wrike folder inside a parent folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_folder_id": {
                        "type": "string",
                        "description": "The parent folder ID",
                    },
                    "title": {
                        "type": "string",
                        "description": "Folder title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional folder description",
                    },
                },
                "required": ["parent_folder_id", "title"],
            },
        ),
        Tool(
            name="get_folder_tasks",
            description="Get all tasks within a specific Wrike folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "string",
                        "description": "The Wrike folder ID",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status",
                        "enum": ["Active", "Completed", "Deferred", "Cancelled"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["folder_id"],
            },
        ),
        Tool(
            name="get_workflows",
            description="List all Wrike workflows and their custom statuses",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_name": {
                        "type": "string",
                        "description": (
                            "Filter by workflow name"
                            " (partial match, case-insensitive)"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_custom_item_types",
            description=(
                "List all Wrike custom item types"
                " (Engineering Project, Spike, Bug Report, etc.)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": (
                            "Filter by type name" " (partial match, case-insensitive)"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_custom_fields",
            description=(
                "List all Wrike custom field definitions"
                " (IDs, types, allowed values)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": (
                            "Filter by field name" " (partial match, case-insensitive)"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="attach_file",
            description="Attach a local file to a Wrike task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Absolute local path to the file to attach",
                    },
                    "file_name": {
                        "type": "string",
                        "description": (
                            "Display name for the attachment"
                            " (defaults to filename from path)"
                        ),
                    },
                },
                "required": ["task_id", "file_path"],
            },
        ),
        Tool(
            name="complete_task",
            description="Mark a Wrike task as completed",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID to complete",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="create_project",
            description=(
                "Create a Wrike project (folder with project"
                " properties) inside a parent folder"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_folder_id": {
                        "type": "string",
                        "description": "The parent folder ID to create the project in",
                    },
                    "title": {
                        "type": "string",
                        "description": "Project title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Project description (HTML allowed)",
                    },
                    "owner_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Contact IDs for project owners",
                    },
                    "custom_status": {
                        "type": "string",
                        "description": "Custom workflow status ID for the project",
                    },
                    "custom_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["id", "value"],
                        },
                        "description": "Custom field values as [{id, value}] pairs",
                    },
                },
                "required": ["parent_folder_id", "title"],
            },
        ),
        Tool(
            name="update_project",
            description="Update an existing Wrike project",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The Wrike project (folder) ID to update",
                    },
                    "title": {
                        "type": "string",
                        "description": "New project title",
                    },
                    "description": {
                        "type": "string",
                        "description": "New project description (HTML allowed)",
                    },
                    "custom_status": {
                        "type": "string",
                        "description": "Custom workflow status ID",
                    },
                    "custom_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["id", "value"],
                        },
                        "description": "Custom field values as [{id, value}] pairs",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="discover_account",
            description=(
                "Discover Wrike account structure: authenticated user, spaces, "
                "folders, workflows (account-level and space-scoped), custom fields, "
                "and item types. Use this to understand the account layout and "
                "identify which folders/workflows to use."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_custom_fields": {
                        "type": "boolean",
                        "description": "Include custom field definitions (default: false)",
                        "default": False,
                    },
                    "include_item_types": {
                        "type": "boolean",
                        "description": "Include custom item type definitions (default: false)",
                        "default": False,
                    },
                    "space_id": {
                        "type": "string",
                        "description": "Only discover a specific space (by ID). Without this, discovers all spaces.",
                    },
                },
            },
        ),
        Tool(
            name="move_task",
            description=(
                "Move a task between folders/projects by adding"
                " or removing parent folders"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The Wrike task ID to move",
                    },
                    "add_parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Folder/project IDs to add the task to",
                    },
                    "remove_parents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Folder/project IDs to remove the task from",
                    },
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    token = get_access_token()
    if not token:
        return [
            TextContent(
                type="text",
                text="Error: Wrike access token not configured.\n\n"
                "To configure, run: `wrike-auth store`\n"
                "Or set environment variable:"
                " `export WRIKE_ACCESS_TOKEN=your_token`\n\n"
                "Get your token from:"
                " https://www.wrike.com/frontend/apps/index.html#/api",
            )
        ]

    try:
        async with WrikeClient(token) as client:
            if name == "search_tasks":
                title = arguments.get("title")
                status = arguments.get("status")
                limit = arguments.get("limit", 50)

                tasks = await client.search_tasks(
                    title=title, status=status, limit=limit
                )

                if not tasks:
                    search_desc = []
                    if title:
                        search_desc.append(f"title='{title}'")
                    if status:
                        search_desc.append(f"status='{status}'")
                    search_str = ", ".join(search_desc) if search_desc else "no filters"
                    return [
                        TextContent(type="text", text=f"No tasks found ({search_str}).")
                    ]

                output = [f"Found {len(tasks)} tasks:\n"]
                for task in tasks:
                    output.append(_format_task(task, include_description=False))
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_task":
                task_id = arguments["task_id"]
                task = await client.get_task(task_id)
                return [TextContent(type="text", text=_format_task(task))]

            elif name == "get_task_comments":
                task_id = arguments["task_id"]
                limit = arguments.get("limit", 50)

                comments = await client.get_task_comments(task_id, limit=limit)

                if not comments:
                    return [
                        TextContent(
                            type="text", text="No comments found for this task."
                        )
                    ]

                # Get author names
                output = [f"**{len(comments)} Comments:**\n"]
                for comment in comments:
                    author_name = await _get_user_name(client, comment.author_id)
                    output.append(_format_comment(comment, author_name))
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_task_attachments":
                task_id = arguments["task_id"]
                limit = arguments.get("limit", 50)

                attachments = await client.get_task_attachments(task_id, limit=limit)

                if not attachments:
                    return [
                        TextContent(
                            type="text", text="No attachments found for this task."
                        )
                    ]

                output = [f"**{len(attachments)} Attachments:**\n"]
                for attachment in attachments:
                    output.append(_format_attachment(attachment))
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_task_full":
                task_id = arguments["task_id"]

                # Fetch task, comments, and attachments in parallel
                task = await client.get_task(task_id)
                comments = await client.get_task_comments(task_id)
                attachments = await client.get_task_attachments(task_id)

                output = [
                    "# Task Details",
                    "",
                    _format_task(task),
                    "",
                ]

                if comments:
                    output.extend(["---", f"## Comments ({len(comments)})", ""])
                    for comment in comments:
                        author_name = await _get_user_name(client, comment.author_id)
                        output.append(_format_comment(comment, author_name))
                        output.append("")

                if attachments:
                    output.extend(["---", f"## Attachments ({len(attachments)})", ""])
                    for attachment in attachments:
                        output.append(_format_attachment(attachment))
                        output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "list_folders":
                limit = arguments.get("limit", 50)
                parent_folder_id = arguments.get("parent_folder_id")
                include_deleted = arguments.get("include_deleted", False)
                folders = await client.get_folders(parent_folder_id=parent_folder_id)

                # Filter out recycle bin items by default
                if not include_deleted:
                    folders = [
                        f for f in folders
                        if f.get("scope", "") not in ("RbFolder", "RbRoot")
                    ]

                if not folders:
                    ctx = f" under `{parent_folder_id}`" if parent_folder_id else ""
                    return [TextContent(type="text", text=f"No folders found{ctx}.")]

                output = [f"Found {len(folders[:limit])} folders:\n"]
                for f in folders[:limit]:
                    title = f.get("title", "Untitled")
                    folder_id = f.get("id", "Unknown")
                    scope = f.get("scope", "")
                    project = f.get("project", {})
                    is_project = bool(project)

                    type_label = "Project" if is_project else "Folder"
                    output.append(f"- **{title}** ({type_label})")
                    output.append(f"  - ID: `{folder_id}`")
                    if scope:
                        output.append(f"  - Scope: {scope}")
                    if is_project:
                        owner_ids = project.get("ownerIds", [])
                        if owner_ids:
                            output.append(f"  - Owners: {', '.join(f'`{o}`' for o in owner_ids)}")
                        status_id = project.get("customStatusId")
                        if status_id:
                            output.append(f"  - Status ID: `{status_id}`")
                    child_ids = f.get("childIds", [])
                    if child_ids:
                        output.append(f"  - Children: {len(child_ids)}")
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "create_task":
                folder_id = arguments["folder_id"]
                title = arguments["title"]

                dates: dict | None = None
                start_date = arguments.get("start_date")
                due_date = arguments.get("due_date")
                if start_date or due_date:
                    dates = {}
                    if start_date:
                        dates["start"] = start_date
                    if due_date:
                        dates["due"] = due_date

                task = await client.create_task(
                    folder_id=folder_id,
                    title=title,
                    description=arguments.get("description"),
                    status=arguments.get("status"),
                    responsible_ids=arguments.get("responsible_ids"),
                    dates=dates,
                    importance=arguments.get("importance"),
                    custom_fields=arguments.get("custom_fields"),
                    custom_status=arguments.get("custom_status"),
                    custom_item_type_id=arguments.get("custom_item_type_id"),
                )

                output = ["**Task created successfully:**\n", _format_task(task)]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "update_task":
                task_id = arguments["task_id"]

                dates = None
                start_date = arguments.get("start_date")
                due_date = arguments.get("due_date")
                if start_date or due_date:
                    dates = {}
                    if start_date:
                        dates["start"] = start_date
                    if due_date:
                        dates["due"] = due_date

                task = await client.update_task(
                    task_id=task_id,
                    title=arguments.get("title"),
                    description=arguments.get("description"),
                    status=arguments.get("status"),
                    add_responsibles=arguments.get("add_responsibles"),
                    remove_responsibles=arguments.get("remove_responsibles"),
                    dates=dates,
                    importance=arguments.get("importance"),
                    completed_date=arguments.get("completed_date"),
                    custom_fields=arguments.get("custom_fields"),
                    custom_status=arguments.get("custom_status"),
                    add_super_tasks=arguments.get("add_super_tasks"),
                    remove_super_tasks=arguments.get("remove_super_tasks"),
                    custom_item_type_id=arguments.get("custom_item_type_id"),
                )

                output = ["**Task updated successfully:**\n", _format_task(task)]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "delete_task":
                task_id = arguments["task_id"]
                await client.delete_task(task_id)
                return [
                    TextContent(
                        type="text", text=f"Task `{task_id}` deleted successfully."
                    )
                ]

            elif name == "create_folder":
                parent_folder_id = arguments["parent_folder_id"]
                title = arguments["title"]

                folder = await client.create_folder(
                    parent_folder_id=parent_folder_id,
                    title=title,
                    description=arguments.get("description"),
                )

                folder_id = folder.get("id", "Unknown")
                folder_title = folder.get("title", title)
                scope = folder.get("scope", "")

                output = [
                    "**Folder created successfully:**\n",
                    f"- **{folder_title}**",
                    f"  - ID: `{folder_id}`",
                ]
                if scope:
                    output.append(f"  - Scope: {scope}")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_folder_tasks":
                folder_id = arguments["folder_id"]
                status = arguments.get("status")
                limit = arguments.get("limit", 50)

                tasks = await client.get_folder_tasks(
                    folder_id=folder_id,
                    status=status,
                    limit=limit,
                )

                if not tasks:
                    filter_desc = f" with status='{status}'" if status else ""
                    return [
                        TextContent(
                            type="text",
                            text=(
                                f"No tasks found in folder"
                                f" `{folder_id}`{filter_desc}."
                            ),
                        )
                    ]

                output = [f"Found {len(tasks)} tasks in folder `{folder_id}`:\n"]
                for task in tasks:
                    output.append(_format_task(task, include_description=False))
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_workflows":
                workflow_name = arguments.get("workflow_name", "").lower()
                workflows = await client.get_workflows()

                output = []
                for wf in workflows:
                    if wf.get("hidden", False):
                        continue
                    name_str = wf.get("name", "Untitled")
                    if workflow_name and workflow_name not in name_str.lower():
                        continue

                    output.append(f"**{name_str}** (ID: `{wf.get('id')}`)")
                    for status in wf.get("customStatuses", []):
                        if status.get("hidden", False):
                            continue
                        output.append(
                            f"  - {status.get('name')} | "
                            f"group: {status.get('group')} | "
                            f"id: `{status.get('id')}`"
                        )
                    output.append("")

                if not output:
                    return [TextContent(type="text", text="No workflows found.")]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_custom_item_types":
                search = arguments.get("search", "").lower()
                item_types = await client.get_custom_item_types()

                output = []
                for it in item_types:
                    title = it.get("title", "Untitled")
                    if search and search not in title.lower():
                        continue
                    related_type = it.get("relatedType", "Unknown")
                    space = it.get("spaceId", "")
                    desc = it.get("description", "")
                    desc_str = f" — {desc}" if desc else ""
                    output.append(
                        f"- **{title}** | {related_type} | "
                        f"id: `{it.get('id')}` | space: `{space}`{desc_str}"
                    )

                if not output:
                    return [
                        TextContent(type="text", text="No custom item types found.")
                    ]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "get_custom_fields":
                search = arguments.get("search", "").lower()
                fields = await client.get_custom_fields()

                output = []
                for f in fields:
                    title = f.get("title", "Untitled")
                    if search and search not in title.lower():
                        continue

                    settings = f.get("settings", {})
                    values = settings.get("values", [])
                    field_type = f.get("type", "Unknown")

                    line = f"**{title}** | type: {field_type} | id: `{f.get('id')}`"
                    output.append(line)
                    if values:
                        output.append(f"  Values: {', '.join(str(v) for v in values)}")

                if not output:
                    return [TextContent(type="text", text="No custom fields found.")]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "attach_file":
                task_id = arguments["task_id"]
                file_path = arguments["file_path"]
                file_name = arguments.get("file_name") or file_path.rsplit("/", 1)[-1]

                attachment = await client.attach_file(
                    task_id=task_id,
                    file_name=file_name,
                    file_path=file_path,
                )

                att_id = attachment.get("id", "Unknown")
                att_name = attachment.get("name", file_name)
                att_size = attachment.get("size", 0)

                return [
                    TextContent(
                        type="text",
                        text=f"**File attached successfully:**\n"
                        f"- Name: {att_name}\n"
                        f"- ID: `{att_id}`\n"
                        f"- Size: {att_size:,} bytes",
                    )
                ]

            elif name == "complete_task":
                task_id = arguments["task_id"]
                task = await client.update_task(task_id=task_id, status="Completed")
                output = ["**Task marked as completed:**\n", _format_task(task)]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "create_project":
                parent_folder_id = arguments["parent_folder_id"]
                title = arguments["title"]

                project = await client.create_project(
                    parent_folder_id=parent_folder_id,
                    title=title,
                    description=arguments.get("description"),
                    owner_ids=arguments.get("owner_ids"),
                    custom_status=arguments.get("custom_status"),
                    custom_fields=arguments.get("custom_fields"),
                )

                output = [
                    "**Project created successfully:**\n",
                    _format_project(project),
                ]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "update_project":
                project_id = arguments["project_id"]

                project = await client.update_project(
                    project_id=project_id,
                    title=arguments.get("title"),
                    description=arguments.get("description"),
                    custom_status=arguments.get("custom_status"),
                    custom_fields=arguments.get("custom_fields"),
                )

                output = [
                    "**Project updated successfully:**\n",
                    _format_project(project),
                ]
                return [TextContent(type="text", text="\n".join(output))]

            elif name == "discover_account":
                include_custom_fields = arguments.get("include_custom_fields", False)
                include_item_types = arguments.get("include_item_types", False)
                filter_space_id = arguments.get("space_id")

                output = []

                # 1. Who am I?
                me = await client.get_me()
                my_id = me["id"]
                my_name = f"{me.get('firstName', '')} {me.get('lastName', '')}".strip()
                my_email = me.get("profiles", [{}])[0].get("email", "")
                output.append("# Wrike Account Discovery\n")
                output.append(f"## Authenticated User")
                output.append(f"- **{my_name}** ({my_email})")
                output.append(f"- Contact ID: `{my_id}`")
                output.append("")

                # 2. Spaces
                spaces = await client.get_spaces()
                if filter_space_id:
                    spaces = [s for s in spaces if s["id"] == filter_space_id]

                output.append(f"## Spaces ({len(spaces)})\n")

                # 3. Account-level workflows
                account_workflows = await client.get_workflows()
                visible_account_wfs = [w for w in account_workflows if not w.get("hidden", False)]

                for space in spaces:
                    space_id = space["id"]
                    space_title = space.get("title", "Untitled")
                    space_type = space.get("accessType", "")
                    members = space.get("members", [])
                    am_member = any(m.get("id") == my_id for m in members)

                    output.append(f"### {space_title}")
                    output.append(f"- ID: `{space_id}`")
                    output.append(f"- Access: {space_type}")
                    output.append(f"- Members: {len(members)}")
                    output.append(f"- I am member: {am_member}")

                    # Get top-level folders in this space (direct children only)
                    try:
                        all_folders = await client.get_folders(space_id=space_id)
                        # Filter recycle bin
                        all_folders = [
                            f for f in all_folders
                            if f.get("scope", "") not in ("RbFolder", "RbRoot")
                        ]
                        # Find space root and its direct children
                        space_root_child_ids = set()
                        for f in all_folders:
                            if f.get("id") == space_id:
                                space_root_child_ids = set(f.get("childIds", []))
                                break
                        folders = [
                            f for f in all_folders
                            if f.get("id") in space_root_child_ids
                        ]
                        total_count = len(all_folders) - 1  # exclude space root itself
                        if folders:
                            output.append(f"- **Top-level folders ({len(folders)} of {total_count} total):**")
                            for f in folders:
                                f_title = f.get("title", "Untitled")
                                f_id = f.get("id", "")
                                wf_id = f.get("workflowId", "")
                                # Resolve workflow name from account + space workflows
                                wf_name = ""
                                for w in account_workflows:
                                    if w["id"] == wf_id:
                                        wf_name = w["name"]
                                        break
                                project = f.get("project", {})
                                is_project = bool(project)
                                type_label = " (Project)" if is_project else ""
                                wf_label = f" | workflow: {wf_name}" if wf_name else ""
                                child_count = len(f.get("childIds", []))
                                children_label = f" | {child_count} children" if child_count else ""
                                output.append(
                                    f"  - `{f_id}` **{f_title}**{type_label}{wf_label}{children_label}"
                                )
                        else:
                            output.append(f"- Folders: {total_count} total (none at top level)")
                    except Exception:
                        output.append("  - (could not list folders)")

                    # Get space-scoped workflows
                    try:
                        space_workflows = await client.get_space_workflows(space_id)
                        if space_workflows:
                            output.append(f"- **Space-scoped Workflows ({len(space_workflows)}):**")
                            for wf in space_workflows:
                                if wf.get("hidden", False):
                                    continue
                                wf_name = wf.get("name", "Untitled")
                                wf_id = wf.get("id", "")
                                statuses = [
                                    s for s in wf.get("customStatuses", [])
                                    if not s.get("hidden", False)
                                ]
                                output.append(f"  - **{wf_name}** (`{wf_id}`) — {len(statuses)} statuses")
                                for s in statuses:
                                    output.append(
                                        f"    - {s.get('name')} | {s.get('group')} | `{s.get('id')}`"
                                    )
                    except Exception:
                        pass  # Space may not support workflows endpoint

                    output.append("")

                # 4. Account-level workflows
                output.append(f"## Account-Level Workflows ({len(visible_account_wfs)})\n")
                for wf in visible_account_wfs:
                    wf_name = wf.get("name", "Untitled")
                    wf_id = wf.get("id", "")
                    is_standard = wf.get("standard", False)
                    std_label = " (standard)" if is_standard else ""
                    statuses = [
                        s for s in wf.get("customStatuses", [])
                        if not s.get("hidden", False)
                    ]
                    output.append(f"### {wf_name}{std_label} (`{wf_id}`)")
                    for s in statuses:
                        output.append(
                            f"- {s.get('name')} | {s.get('group')} | `{s.get('id')}`"
                        )
                    output.append("")

                # 5. Custom fields (optional)
                if include_custom_fields:
                    fields = await client.get_custom_fields()
                    output.append(f"## Custom Fields ({len(fields)})\n")
                    for f in fields:
                        title = f.get("title", "Untitled")
                        field_type = f.get("type", "Unknown")
                        settings = f.get("settings", {})
                        values = settings.get("values", [])
                        line = f"- **{title}** | {field_type} | `{f.get('id')}`"
                        if values:
                            line += f" | values: {', '.join(str(v) for v in values[:10])}"
                            if len(values) > 10:
                                line += f" (+{len(values)-10} more)"
                        output.append(line)
                    output.append("")

                # 6. Custom item types (optional)
                if include_item_types:
                    item_types = await client.get_custom_item_types()
                    output.append(f"## Custom Item Types ({len(item_types)})\n")
                    for it in item_types:
                        title = it.get("title", "Untitled")
                        related = it.get("relatedType", "Unknown")
                        space = it.get("spaceId", "")
                        output.append(
                            f"- **{title}** | {related} | `{it.get('id')}` | space: `{space}`"
                        )
                    output.append("")

                return [TextContent(type="text", text="\n".join(output))]

            elif name == "move_task":
                task_id = arguments["task_id"]

                task = await client.move_task(
                    task_id=task_id,
                    add_parents=arguments.get("add_parents"),
                    remove_parents=arguments.get("remove_parents"),
                )

                output = [
                    "**Task moved successfully:**\n",
                    _format_task(task, include_description=False),
                ]
                return [TextContent(type="text", text="\n".join(output))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


def main():
    """Run the MCP server."""

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
