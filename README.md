# mcp-wrike

MCP (Model Context Protocol) server for Wrike project management. Full CRUD support for tasks, folders, spaces, and attachments with account discovery for bootstrapping.

## Features

### Discovery
- **discover_account** — Bootstrap tool: identifies authenticated user, enumerates spaces, lists top-level folders with workflow assignments, catalogues account-level and space-scoped workflows, and optionally includes custom fields and item types

### Read
- **search_tasks** — Search tasks by title or status
- **get_task** — Get detailed task information
- **get_task_comments** — View comments/notes on a task
- **get_task_attachments** — List task attachments
- **get_task_full** — Complete view: task + comments + attachments
- **get_workflows** — List all account-level workflows and their custom statuses
- **get_custom_fields** — List all custom field definitions
- **get_custom_item_types** — List all custom item type definitions
- **list_folders** — Browse Wrike folders/projects
- **get_folder_tasks** — List tasks within a folder (supports `recursive=true` to include child folder/project tasks)

### Write
- **create_task** — Create tasks with title, description, status, assignees, dates, importance, custom fields, and custom item types
- **update_task** — Update any task field including custom fields
- **complete_task** — Mark a task as completed
- **move_task** — Move a task between folders (add/remove parents)
- **delete_task** — Delete a task permanently
- **create_folder** — Create subfolders
- **delete_folder** — Delete a folder permanently
- **delete_space** — Delete a space permanently
- **attach_file** — Upload local files as task attachments

## Installation

```bash
# Install from source
cd mcp-wrike
pip install -e .
```

## Configuration

### Get your Wrike Access Token

1. Go to https://www.wrike.com/frontend/apps/index.html#/api
2. Create a new "Permanent Access Token"
3. Copy the token

### Store the token

Option 1 — System keychain (recommended):
```bash
wrike-auth store
# Enter your token when prompted
```

Option 2 — Environment variable:
```bash
export WRIKE_ACCESS_TOKEN=your_token_here
```

### Check configuration
```bash
wrike-auth show
```

## Claude Code Integration

Add to your `.claude/settings.local.json` MCP configuration:

```json
{
  "mcpServers": {
    "wrike": {
      "command": "mcp-wrike"
    }
  }
}
```

Or in `claude_desktop_config.json` for Claude Desktop:

```json
{
  "mcpServers": {
    "wrike": {
      "command": "mcp-wrike"
    }
  }
}
```

## Account Discovery (Bootstrap)

The `discover_account` tool provides a comprehensive view of your Wrike account structure. Use it to identify folder IDs, workflow status IDs, custom fields, and item types needed for task management.

### What it discovers

- **Authenticated user** — name, email, contact ID
- **Spaces** — all spaces with access type and member count
- **Top-level folders per space** — filtered to direct children only (not the full recursive tree), with workflow assignments resolved by name
- **Space-scoped workflows** — workflows belonging to specific spaces (not returned by the account-level workflows endpoint)
- **Account-level workflows** — all 40+ shared workflows with custom status IDs
- **Custom fields** (optional) — field definitions with types and allowed values
- **Custom item types** (optional) — task type definitions (Project, Task, Bug, Spike, Epic, etc.)

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `space_id` | — | Filter to a single space by ID |
| `include_custom_fields` | false | Include custom field definitions |
| `include_item_types` | false | Include custom item type definitions |

### Workflow scoping

Wrike workflows can be scoped to either the account level or to specific spaces. The `discover_account` tool checks both:

- **Account-level**: `GET /workflows` — shared across all spaces
- **Space-scoped**: `GET /spaces/{id}/workflows` — belong to a specific space

This matters because a folder's `workflowId` may reference a space-scoped workflow that doesn't appear in the account-level listing.

## Custom Fields

`create_task` and `update_task` support Wrike custom fields via the `custom_fields` parameter:

```json
{
  "custom_fields": [
    {"id": "FIELD_ID", "value": "field value"}
  ]
}
```

Use `discover_account` with `include_custom_fields=true` to list all available field IDs, or query the Wrike API directly: `GET /customfields`.

## Custom Item Types

Tasks can be assigned a custom item type at creation via the `custom_item_type_id` parameter. Item types cannot be changed after creation.

Use `discover_account` with `include_item_types=true` to list available types.

## Usage Examples

Once configured, you can ask Claude:

- "Discover my Wrike account structure"
- "Search for active tasks about 'deployment'"
- "Create a task in folder X titled 'Fix the bug'"
- "Mark task IEAABCD123 as completed"
- "Move the task to the Engineering folder"
- "Attach this spec file to the Wrike task"
- "Show me all tasks in the Engineering folder"
- "Delete the empty test folder"

## License

MIT
