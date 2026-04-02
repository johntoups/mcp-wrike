"""Wrike API client."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

BASE_URL = "https://www.wrike.com/api/v4"


@dataclass
class WrikeTask:
    """Wrike task data."""

    id: str
    title: str
    status: str
    importance: str | None
    created_date: datetime | None
    updated_date: datetime | None
    completed_date: datetime | None
    dates: dict | None  # start, due, duration
    scope: str | None  # folder/project ID
    description: str | None
    brief_description: str | None
    parent_ids: list[str] = field(default_factory=list)
    super_task_ids: list[str] = field(default_factory=list)
    responsible_ids: list[str] = field(default_factory=list)
    permalink: str | None = None
    priority: str | None = None
    custom_fields: list[dict] = field(default_factory=list)
    custom_status_id: str | None = None
    custom_status_name: str | None = None


@dataclass
class WrikeComment:
    """Wrike comment data."""

    id: str
    author_id: str
    text: str
    created_date: datetime | None
    task_id: str | None = None


@dataclass
class WrikeAttachment:
    """Wrike attachment data."""

    id: str
    name: str
    size: int | None
    created_date: datetime | None
    content_type: str | None
    author_id: str | None
    task_id: str | None = None
    url: str | None = None


@dataclass
class WrikeProject:
    """Wrike project data (a folder with project properties)."""

    id: str
    title: str
    description: str | None
    custom_status_id: str | None
    custom_status_name: str | None
    owner_ids: list[str] = field(default_factory=list)
    created_date: datetime | None = None
    updated_date: datetime | None = None
    permalink: str | None = None
    child_ids: list[str] = field(default_factory=list)
    custom_fields: list[dict] = field(default_factory=list)


class WrikeClient:
    """Async client for Wrike REST API."""

    def __init__(self, access_token: str):
        """Initialize client with access token.

        Args:
            access_token: Wrike OAuth 2.0 access token
        """
        self.access_token = access_token
        self._client: httpx.AsyncClient | None = None
        self._status_cache: dict[str, str] = {}  # status_id -> name

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> dict[str, Any]:
        """Execute API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body for POST/PUT

        Returns:
            Response data

        Raises:
            httpx.HTTPError: On request failure
            ValueError: On API errors
        """
        if not self._client:
            raise RuntimeError(
                "Client not initialized. Use 'async with' context manager."
            )

        url = f"{BASE_URL}{endpoint}"
        response = await self._client.request(
            method, url, params=params, json=json_data
        )
        response.raise_for_status()

        data = response.json()
        if "errorDescription" in data:
            raise ValueError(f"Wrike API error: {data['errorDescription']}")

        return data

    def _parse_datetime(self, dt_str: str | None) -> datetime | None:
        """Parse Wrike datetime string."""
        if not dt_str:
            return None
        try:
            # Wrike uses ISO 8601 format
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    async def search_tasks(
        self,
        title: str | None = None,
        status: str | None = None,
        folder_id: str | None = None,
        limit: int = 100,
    ) -> list[WrikeTask]:
        """Search for tasks.

        Args:
            title: Search by title (partial match)
            status: Filter by status (Active, Completed, Deferred, Cancelled)
            folder_id: Filter by folder/project ID
            limit: Maximum results (API max is 1000)

        Returns:
            List of matching tasks
        """
        params: dict[str, Any] = {
            "pageSize": min(limit, 1000),
            "fields": '["parentIds"]',
        }

        if title:
            params["title"] = title
        if status:
            params["status"] = status

        if folder_id:
            endpoint = f"/folders/{folder_id}/tasks"
        else:
            endpoint = "/tasks"

        data = await self._request("GET", endpoint, params=params)
        await self._ensure_status_cache()

        tasks = []
        for t in data.get("data", []):
            tasks.append(self._parse_task(t))

        return tasks

    async def _ensure_status_cache(self) -> None:
        """Load workflow statuses into cache if not already loaded."""
        if not self._status_cache:
            await self.get_workflows()

    def _parse_task(self, t: dict) -> WrikeTask:
        """Parse task from API response."""
        # Resolve custom status name from cached workflows
        custom_status_id = t.get("customStatusId")
        custom_status_name = (
            self._status_cache.get(custom_status_id) if custom_status_id else None
        )

        return WrikeTask(
            id=t["id"],
            title=t.get("title", "Untitled"),
            status=t.get("status", "Unknown"),
            importance=t.get("importance"),
            created_date=self._parse_datetime(t.get("createdDate")),
            updated_date=self._parse_datetime(t.get("updatedDate")),
            completed_date=self._parse_datetime(t.get("completedDate")),
            dates=t.get("dates"),
            scope=t.get("scope"),
            description=t.get("description"),
            brief_description=t.get("briefDescription"),
            parent_ids=t.get("parentIds", []),
            super_task_ids=t.get("superTaskIds", []),
            responsible_ids=t.get("responsibleIds", []),
            permalink=t.get("permalink"),
            priority=t.get("priority"),
            custom_fields=t.get("customFields", []),
            custom_status_id=custom_status_id,
            custom_status_name=custom_status_name,
        )

    async def get_task(self, task_id: str) -> WrikeTask:
        """Get task by ID.

        Args:
            task_id: Wrike task ID

        Returns:
            Task details
        """
        # Request additional fields via query param
        data = await self._request("GET", f"/tasks/{task_id}")
        await self._ensure_status_cache()

        tasks = data.get("data", [])
        if not tasks:
            raise ValueError(f"Task not found: {task_id}")

        return self._parse_task(tasks[0])

    async def get_task_comments(
        self, task_id: str, limit: int = 100
    ) -> list[WrikeComment]:
        """Get comments for a task.

        Args:
            task_id: Wrike task ID
            limit: Maximum comments to return

        Returns:
            List of comments
        """
        data = await self._request("GET", f"/tasks/{task_id}/comments")

        comments = []
        for c in data.get("data", []):
            comments.append(
                WrikeComment(
                    id=c["id"],
                    author_id=c.get("authorId", "Unknown"),
                    text=c.get("text", ""),
                    created_date=self._parse_datetime(c.get("createdDate")),
                    task_id=task_id,
                )
            )

        return comments

    async def get_task_attachments(
        self, task_id: str, limit: int = 100
    ) -> list[WrikeAttachment]:
        """Get attachments for a task.

        Args:
            task_id: Wrike task ID
            limit: Maximum attachments to return

        Returns:
            List of attachments
        """
        data = await self._request("GET", f"/tasks/{task_id}/attachments")

        attachments = []
        for a in data.get("data", []):
            attachments.append(
                WrikeAttachment(
                    id=a["id"],
                    name=a.get("name", "Unknown"),
                    size=a.get("size"),
                    created_date=self._parse_datetime(a.get("createdDate")),
                    content_type=a.get("contentType"),
                    author_id=a.get("authorId"),
                    task_id=task_id,
                    url=a.get("url"),
                )
            )

        return attachments

    async def get_attachment_url(self, attachment_id: str) -> str | None:
        """Get download URL for an attachment.

        Args:
            attachment_id: Wrike attachment ID

        Returns:
            Download URL or None
        """
        data = await self._request("GET", f"/attachments/{attachment_id}/url")
        items = data.get("data", [])
        if items:
            return items[0].get("url")
        return None

    async def get_folders(
        self,
        space_id: str | None = None,
        parent_folder_id: str | None = None,
    ) -> list[dict]:
        """Get folders/projects.

        Args:
            space_id: Optional space ID to filter by
            parent_folder_id: Optional parent folder ID to list children of

        Returns:
            List of folder metadata
        """
        if parent_folder_id:
            endpoint = f"/folders/{parent_folder_id}/folders"
        elif space_id:
            endpoint = f"/spaces/{space_id}/folders"
        else:
            endpoint = "/folders"

        data = await self._request("GET", endpoint)
        return data.get("data", [])

    async def get_contacts(self, limit: int = 100) -> list[dict]:
        """Get contacts (users) in the account.

        Returns:
            List of contact metadata with id, firstName, lastName, email
        """
        data = await self._request("GET", "/contacts")
        return data.get("data", [])

    async def create_task(
        self,
        folder_id: str,
        title: str,
        description: str | None = None,
        status: str | None = None,
        responsible_ids: list[str] | None = None,
        dates: dict | None = None,
        importance: str | None = None,
        custom_fields: list[dict] | None = None,
        custom_status: str | None = None,
        custom_item_type_id: str | None = None,
    ) -> WrikeTask:
        """Create a new task in a folder.

        Args:
            folder_id: Parent folder ID
            title: Task title
            description: Task description (HTML allowed)
            status: Active, Completed, Deferred, or Cancelled
            responsible_ids: List of contact IDs to assign
            dates: Dict with optional 'start' and 'due' keys (YYYY-MM-DD)
            importance: High, Normal, or Low
            custom_status: Custom workflow status ID (overrides status)
            custom_item_type_id: Custom item type ID

        Returns:
            Created task
        """
        body: dict[str, Any] = {"title": title}

        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if responsible_ids:
            body["responsibles"] = responsible_ids
        if dates:
            body["dates"] = dates
        if importance is not None:
            body["importance"] = importance
        if custom_fields:
            body["customFields"] = custom_fields
        if custom_status:
            body["customStatus"] = custom_status
        if custom_item_type_id:
            body["customItemTypeId"] = custom_item_type_id

        data = await self._request(
            "POST", f"/folders/{folder_id}/tasks", json_data=body
        )
        await self._ensure_status_cache()
        tasks = data.get("data", [])
        if not tasks:
            raise ValueError("Task creation returned no data")
        return self._parse_task(tasks[0])

    async def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        add_responsibles: list[str] | None = None,
        remove_responsibles: list[str] | None = None,
        dates: dict | None = None,
        importance: str | None = None,
        completed_date: str | None = None,
        custom_fields: list[dict] | None = None,
        custom_status: str | None = None,
        add_super_tasks: list[str] | None = None,
        remove_super_tasks: list[str] | None = None,
        custom_item_type_id: str | None = None,
    ) -> WrikeTask:
        """Update an existing task.

        Args:
            task_id: Wrike task ID
            title: New title
            description: New description (HTML allowed)
            status: New status (Active, Completed, Deferred, Cancelled)
            add_responsibles: Contact IDs to add as assignees
            remove_responsibles: Contact IDs to remove as assignees
            dates: Dict with optional 'start' and 'due' keys (YYYY-MM-DD)
            importance: High, Normal, or Low
            completed_date: Completion date override (YYYY-MM-DD)
            custom_status: Custom workflow status ID (overrides status)
            add_super_tasks: Task IDs to add as parent tasks
            remove_super_tasks: Task IDs to remove as parent tasks
            custom_item_type_id: Custom item type ID

        Returns:
            Updated task
        """
        body: dict[str, Any] = {}

        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if status is not None:
            body["status"] = status
        if add_responsibles:
            body["addResponsibles"] = add_responsibles
        if remove_responsibles:
            body["removeResponsibles"] = remove_responsibles
        if dates:
            body["dates"] = dates
        if importance is not None:
            body["importance"] = importance
        if completed_date is not None:
            body["completedDate"] = completed_date
        if custom_fields:
            body["customFields"] = custom_fields
        if custom_status:
            body["customStatus"] = custom_status
        if add_super_tasks:
            body["addSuperTasks"] = add_super_tasks
        if remove_super_tasks:
            body["removeSuperTasks"] = remove_super_tasks
        if custom_item_type_id:
            body["customItemTypeId"] = custom_item_type_id

        data = await self._request("PUT", f"/tasks/{task_id}", json_data=body)
        await self._ensure_status_cache()
        tasks = data.get("data", [])
        if not tasks:
            raise ValueError(f"Task update returned no data for task: {task_id}")
        return self._parse_task(tasks[0])

    async def delete_task(self, task_id: str) -> None:
        """Delete a task.

        Args:
            task_id: Wrike task ID

        Raises:
            ValueError: If the API returns an error
        """
        await self._request("DELETE", f"/tasks/{task_id}")

    async def create_folder(
        self,
        parent_folder_id: str,
        title: str,
        description: str | None = None,
    ) -> dict:
        """Create a new folder inside a parent folder.

        Args:
            parent_folder_id: Parent folder ID
            title: Folder title
            description: Optional folder description

        Returns:
            Created folder metadata
        """
        body: dict[str, Any] = {"title": title}

        if description is not None:
            body["description"] = description

        data = await self._request(
            "POST", f"/folders/{parent_folder_id}/folders", json_data=body
        )
        folders = data.get("data", [])
        if not folders:
            raise ValueError("Folder creation returned no data")
        return folders[0]

    async def attach_file(
        self,
        task_id: str,
        file_name: str,
        file_path: str,
    ) -> dict:
        """Attach a file to a task.

        Args:
            task_id: Wrike task ID
            file_name: Display name for the attachment
            file_path: Local path to the file to upload

        Returns:
            Attachment metadata
        """
        if not self._client:
            raise RuntimeError(
                "Client not initialized. Use 'async with' context manager."
            )

        with open(file_path, "rb") as f:
            content = f.read()

        url = f"{BASE_URL}/tasks/{task_id}/attachments"
        response = await self._client.post(
            url,
            headers={"X-File-Name": file_name},
            content=content,
        )
        response.raise_for_status()

        data = response.json()
        if "errorDescription" in data:
            raise ValueError(f"Wrike API error: {data['errorDescription']}")

        attachments = data.get("data", [])
        if not attachments:
            raise ValueError("Attachment upload returned no data")
        return attachments[0]

    async def get_workflows(self) -> list[dict]:
        """Get all workflows and their custom statuses.

        Returns:
            List of workflow dicts with id, name, customStatuses
        """
        data = await self._request("GET", "/workflows")
        workflows = data.get("data", [])

        # Populate status cache
        for wf in workflows:
            for status in wf.get("customStatuses", []):
                self._status_cache[status["id"]] = status.get("name", "Unknown")

        return workflows

    async def get_custom_item_types(self) -> list[dict]:
        """Get all custom item type definitions.

        Returns:
            List of custom item type dicts with id, title, type, etc.
        """
        data = await self._request("GET", "/custom_item_types")
        return data.get("data", [])

    async def get_custom_fields(self) -> list[dict]:
        """Get all custom field definitions.

        Returns:
            List of custom field dicts with id, title, type, settings
        """
        data = await self._request("GET", "/customfields")
        return data.get("data", [])

    async def get_folder_tasks(
        self,
        folder_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[WrikeTask]:
        """Get tasks within a specific folder.

        Args:
            folder_id: Wrike folder ID
            status: Optional status filter (Active, Completed, Deferred, Cancelled)
            limit: Maximum results

        Returns:
            List of tasks in the folder
        """
        params: dict[str, Any] = {
            "pageSize": min(limit, 1000),
            "fields": '["parentIds"]',
        }
        if status:
            params["status"] = status

        data = await self._request("GET", f"/folders/{folder_id}/tasks", params=params)
        await self._ensure_status_cache()
        return [self._parse_task(t) for t in data.get("data", [])]

    async def create_project(
        self,
        parent_folder_id: str,
        title: str,
        description: str | None = None,
        owner_ids: list[str] | None = None,
        custom_status: str | None = None,
        custom_fields: list[dict] | None = None,
    ) -> WrikeProject:
        """Create a new project (folder with project properties).

        Args:
            parent_folder_id: Parent folder ID
            title: Project title
            description: Project description (HTML allowed)
            owner_ids: Contact IDs for project owners
            custom_status: Custom workflow status ID for the project
            custom_fields: Custom field values as [{id, value}] pairs

        Returns:
            Created project
        """
        project_params: dict[str, Any] = {}
        if owner_ids:
            project_params["ownerIds"] = owner_ids
        if custom_status:
            project_params["customStatusId"] = custom_status

        body: dict[str, Any] = {
            "title": title,
            "project": project_params,
        }

        if description is not None:
            body["description"] = description
        if custom_fields:
            body["customFields"] = custom_fields

        data = await self._request(
            "POST", f"/folders/{parent_folder_id}/folders", json_data=body
        )
        await self._ensure_status_cache()
        folders = data.get("data", [])
        if not folders:
            raise ValueError("Project creation returned no data")
        return self._parse_project(folders[0])

    async def update_project(
        self,
        project_id: str,
        title: str | None = None,
        description: str | None = None,
        custom_status: str | None = None,
        custom_fields: list[dict] | None = None,
    ) -> WrikeProject:
        """Update an existing project.

        Args:
            project_id: Wrike project (folder) ID
            title: New title
            description: New description (HTML allowed)
            custom_status: Custom workflow status ID
            custom_fields: Custom field values as [{id, value}] pairs

        Returns:
            Updated project
        """
        body: dict[str, Any] = {}

        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if custom_status:
            body["project"] = {"customStatusId": custom_status}
        if custom_fields:
            body["customFields"] = custom_fields

        data = await self._request("PUT", f"/folders/{project_id}", json_data=body)
        await self._ensure_status_cache()
        folders = data.get("data", [])
        if not folders:
            raise ValueError(f"Project update returned no data for: {project_id}")
        return self._parse_project(folders[0])

    async def move_task(
        self,
        task_id: str,
        add_parents: list[str] | None = None,
        remove_parents: list[str] | None = None,
    ) -> WrikeTask:
        """Move a task between folders/projects.

        Args:
            task_id: Wrike task ID
            add_parents: Folder/project IDs to add the task to
            remove_parents: Folder/project IDs to remove the task from

        Returns:
            Updated task
        """
        body: dict[str, Any] = {}
        if add_parents:
            body["addParents"] = add_parents
        if remove_parents:
            body["removeParents"] = remove_parents

        data = await self._request("PUT", f"/tasks/{task_id}", json_data=body)
        await self._ensure_status_cache()
        tasks = data.get("data", [])
        if not tasks:
            raise ValueError(f"Task move returned no data for: {task_id}")
        return self._parse_task(tasks[0])

    def _parse_project(self, f: dict) -> WrikeProject:
        """Parse project from API response."""
        project_data = f.get("project", {})
        custom_status_id = project_data.get("customStatusId")
        custom_status_name = (
            self._status_cache.get(custom_status_id) if custom_status_id else None
        )

        return WrikeProject(
            id=f["id"],
            title=f.get("title", "Untitled"),
            description=f.get("description"),
            custom_status_id=custom_status_id,
            custom_status_name=custom_status_name,
            owner_ids=project_data.get("ownerIds", []),
            created_date=self._parse_datetime(project_data.get("createdDate")),
            updated_date=self._parse_datetime(f.get("updatedDate")),
            permalink=f.get("permalink"),
            child_ids=f.get("childIds", []),
            custom_fields=f.get("customFields", []),
        )
