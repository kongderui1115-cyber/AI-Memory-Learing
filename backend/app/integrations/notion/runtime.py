"""Current Notion API reader with complete block and query pagination."""

from urllib.parse import quote

from app.ai.errors import ProviderResponseError

from .client import NOTION_API_BASE, NotionClient, parse_query_response
from .markdown import blocks_to_markdown


class RuntimeNotionClient(NotionClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._block_cache = {}

    def children(self, block_id):
        if block_id in self._block_cache:
            return self._block_cache[block_id]
        blocks = []
        cursor = None
        seen = set()
        while True:
            url = f"{NOTION_API_BASE}/blocks/{quote(block_id, safe='')}/children?page_size=100"
            if cursor:
                url += "&start_cursor=" + quote(cursor, safe="")
            result = self._request_json("GET", url, None)
            if not isinstance(result.get("results"), list):
                raise ProviderResponseError("Notion block response has no results list")
            blocks.extend(result["results"])
            if len(blocks) > 10000:
                raise ProviderResponseError("Notion block limit exceeded for one container")
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")
            if not cursor or cursor in seen:
                raise ProviderResponseError("Notion returned an invalid pagination cursor")
            seen.add(cursor)
        self._block_cache[block_id] = blocks
        return blocks

    def page_blocks(self, page_id):
        expanded = []
        visited = set()

        def collect(block_id, depth):
            if depth > 100 or block_id in visited:
                raise ProviderResponseError("Notion block tree contains excessive depth or a cycle")
            visited.add(block_id)
            for block in self.children(block_id):
                expanded.append(block)
                if len(expanded) > 10000:
                    raise ProviderResponseError("Notion page block limit exceeded")
                if block.get("has_children") and block.get("type") not in {
                    "child_page",
                    "child_database",
                }:
                    collect(str(block["id"]), depth + 1)

        collect(page_id, 0)
        return expanded

    def markdown(self, page_id):
        return blocks_to_markdown(self.page_blocks(page_id))

    def query(self, source_type, external_id, *, watermark=None, cursor=None):
        body = self.query_database_body(start_cursor=cursor)
        if watermark:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"on_or_after": watermark},
            }
        identifier = quote(external_id, safe="")
        if source_type == "database" and self.api_version >= "2025-09-03":
            database = self._request_json("GET", f"{NOTION_API_BASE}/databases/{identifier}", None)
            sources = database.get("data_sources", [])
            if len(sources) != 1:
                raise ProviderResponseError("Select an explicit data_source ID for this database")
            identifier = quote(sources[0]["id"], safe="")
            source_type = "data_source"
        collection = "data_sources" if source_type == "data_source" else "databases"
        if source_type == "data_source" and self.api_version >= "2026-03-11":
            body["archive_status"] = "all"
        payload = self._request_json(
            "POST", f"{NOTION_API_BASE}/{collection}/{identifier}/query", body
        )
        status = payload.get("request_status")
        if isinstance(status, dict) and status.get("type") == "incomplete":
            raise ProviderResponseError("Notion query was incomplete")
        result = parse_query_response(
            payload, include_archived=True
        )
        if result.has_more and not result.next_cursor:
            raise ProviderResponseError("Notion query has more pages without a cursor")
        return result

    def retrieve_page(self, page_id):
        payload = self._request_json(
            "GET", f"{NOTION_API_BASE}/pages/{quote(page_id, safe='')}", None
        )
        pages = parse_query_response({"results": [payload]}, include_archived=True).pages
        if not pages or pages[0].external_page_id.replace("-", "") != page_id.replace("-", ""):
            raise ProviderResponseError("Notion page response has no matching page")
        return pages[0]

    def page_tree(self, root_id):
        pending = [root_id]
        seen = set()
        pages = []
        while pending:
            page_id = pending.pop(0)
            if page_id in seen:
                continue
            seen.add(page_id)
            if len(seen) > 1000:
                raise ProviderResponseError("Page tree exceeds 1000 pages, use a database source")
            page = self.retrieve_page(page_id)
            pages.append(page)
            if page.is_archived:
                continue
            for block in self.page_blocks(page_id):
                if block.get("type") == "child_page":
                    pending.append(str(block["id"]))
        return pages
