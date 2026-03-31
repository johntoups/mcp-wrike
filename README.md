# mcp-wrike

MCP (Model Context Protocol) server for Wrike project management. Full CRUD support for tasks, folders, and attachments.

## Features

### Read
- **search_tasks** — Search tasks by title or status
- **get_task** — Get detailed task information
- **get_task_comments** — View comments/notes on a task
- **get_task_attachments** — List task attachments
- **get_task_full** — Complete view: task + comments + attachments
- **list_folders** — Browse Wrike folders/projects
- **get_folder_tasks** — List tasks within a folder

### Write
- **create_task** — Create tasks with title, description, status, assignees, dates, importance, and custom fields
- **update_task** — Update any task field including custom fields
- **complete_task** — Mark a task as completed
- **delete_task** — Delete a task permanently
- **create_folder** — Create subfolders
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

## Custom Fields

`create_task` and `update_task` support Wrike custom fields via the `custom_fields` parameter:

```json
{
  "custom_fields": [
    {"id": "FIELD_ID", "value": "field value"}
  ]
}
```

Get your custom field IDs from the Wrike API: `GET /customfields`

## Usage Examples

Once configured, you can ask Claude:

- "Search for active tasks about 'deployment'"
- "Create a task in folder X titled 'Fix the bug'"
- "Mark task IEAABCD123 as completed"
- "Attach this spec file to the Wrike task"
- "Show me all tasks in the Engineering folder"

## License

MIT
