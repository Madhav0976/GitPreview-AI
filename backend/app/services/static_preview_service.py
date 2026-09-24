"""
Static Preview Service (GitPreview-AI V2 - Phase 2)

Inspects repository trees to discover static HTML entry points and provides
secure, read-only static asset resolution and HTML base tag injection.
Treats all repository code as UNTRUSTED DATA. Zero code execution.
"""

import json
import logging
import os
import posixpath
import re
import urllib.parse
from typing import Dict, Any, List, Set, Optional, Tuple

import httpx
from fastapi import HTTPException

from app.models import PreviewDetectResponse
from app.services.github_client import (
    fetch_file_bytes,
    fetch_file_content,
    rate_limit_tracker,
)

logger = logging.getLogger(__name__)

# Size limits
MAX_CODE_SIZE_BYTES = 2 * 1024 * 1024    # 2 MB for HTML, CSS, JS, JSON
MAX_MEDIA_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB for Images, Fonts

# Strict MIME type mapping for whitelisted static extensions
STATIC_MIME_TYPES: Dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".bmp": "image/bmp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".xml": "application/xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

# Blacklist of prohibited sensitive/server/executable extensions
BLOCKED_EXTENSIONS: Set[str] = {
    ".env", ".key", ".pem", ".crt", ".cert", ".p12", ".pfx",
    ".py", ".sh", ".exe", ".bat", ".cmd", ".ps1", ".rb", ".php",
    ".go", ".rs", ".java", ".c", ".cpp", ".cs", ".swift",
    ".tar", ".zip", ".gz", ".7z", ".rar",
}

# Framework/tool indicators that require a build or server runtime
UNSUPPORTED_FRAMEWORK_SIGNATURES: Set[str] = {
    "next", "vite", "react-scripts", "@angular/core", "@vue/cli-service",
    "@sveltejs/kit", "nuxt", "express", "@nestjs/core", "fastapi", "flask", "django"
}


def resolve_entry_point(all_paths: Set[str]) -> Optional[str]:
    """
    Resolve static HTML entry point using Git tree paths by strict priority:
    1. root index.html
    2. root index.htm
    3. public/index.html
    4. dist/index.html
    5. build/index.html
    6. one unambiguous root-level HTML file
    """
    path_map = {p.lower(): p for p in all_paths}

    priority_candidates = [
        "index.html",
        "index.htm",
        "public/index.html",
        "dist/index.html",
        "build/index.html",
    ]

    for cand in priority_candidates:
        if cand in path_map:
            return path_map[cand]

    # Priority 6: Check for single unambiguous root-level HTML file
    root_html_files = [
        p for p in all_paths
        if "/" not in p and p.lower().endswith((".html", ".htm"))
    ]
    if len(root_html_files) == 1:
        return root_html_files[0]

    # Multiple root HTML files without an index, or no HTML files
    return None


async def detect_static_preview(
    owner: str,
    repo_name: str,
    default_branch: str,
    tree_entries: List[Dict[str, Any]],
    languages: Dict[str, int],
    client: httpx.AsyncClient,
) -> PreviewDetectResponse:
    """
    Check if a repository can be previewed as a static website.
    Verifies that the repo does not require a build tool or dynamic server runtime.
    """
    all_paths = {entry.get("path", "") for entry in tree_entries if entry.get("path")}
    root_files = {p for p in all_paths if "/" not in p}

    # 1. Check for dynamic server runtimes or package manager build systems
    # Python
    if any(p in root_files or f"backend/{p}" in all_paths for p in ("requirements.txt", "pyproject.toml", "Pipfile", "manage.py")):
        return PreviewDetectResponse(
            status="UNSUPPORTED",
            category="backend API",
            entryPoint=None,
            previewUrl=None,
            totalAssets=0,
            detectedAssets=[],
            blockers=["This repository requires a live server runtime (Python) and cannot be previewed as a static site."]
        )

    # Go, Rust, Java
    if "go.mod" in root_files:
        return PreviewDetectResponse(
            status="UNSUPPORTED",
            category="backend API",
            entryPoint=None,
            previewUrl=None,
            totalAssets=0,
            detectedAssets=[],
            blockers=["This repository is written in Go and requires compilation/runtime execution."]
        )
    if "Cargo.toml" in root_files:
        return PreviewDetectResponse(
            status="UNSUPPORTED",
            category="CLI",
            entryPoint=None,
            previewUrl=None,
            totalAssets=0,
            detectedAssets=[],
            blockers=["This repository is written in Rust and requires compilation/runtime execution."]
        )
    if "pom.xml" in root_files or "build.gradle" in root_files or "build.gradle.kts" in root_files:
        return PreviewDetectResponse(
            status="UNSUPPORTED",
            category="backend API",
            entryPoint=None,
            previewUrl=None,
            totalAssets=0,
            detectedAssets=[],
            blockers=["This repository is written in Java and requires compilation/runtime execution."]
        )

    # Node.js build tools (Vite, Next.js, CRA, Angular, etc.)
    if "package.json" in root_files or "frontend/package.json" in all_paths:
        pkg_path = "package.json" if "package.json" in root_files else "frontend/package.json"
        pkg_content = await fetch_file_content(owner, repo_name, pkg_path, client, default_branch)
        try:
            pkg_data = json.loads(pkg_content) if pkg_content else {}
            deps = pkg_data.get("dependencies") or {}
            dev_deps = pkg_data.get("devDependencies") or {}
            scripts = pkg_data.get("scripts") or {}
            all_deps = {**deps, **dev_deps}

            # Check if it requires a build or framework runtime
            if any(sig in all_deps for sig in UNSUPPORTED_FRAMEWORK_SIGNATURES) or "build" in scripts:
                category = "frontend"
                if "next" in all_deps:
                    category = "full-stack"
                elif "express" in all_deps or "@nestjs/core" in all_deps:
                    category = "backend API"
                return PreviewDetectResponse(
                    status="UNSUPPORTED",
                    category=category,
                    entryPoint=None,
                    previewUrl=None,
                    totalAssets=0,
                    detectedAssets=[],
                    blockers=[f"This repository requires a client-side build step ({category}) before it can be rendered."]
                )
        except Exception:
            pass

    # 2. Resolve HTML entry point
    entry_point = resolve_entry_point(all_paths)
    if not entry_point:
        root_htmls = [p for p in all_paths if "/" not in p and p.lower().endswith((".html", ".htm"))]
        if len(root_htmls) > 1:
            blocker = f"Multiple root HTML files detected ({', '.join(root_htmls[:3])}) without a default index.html entry point."
        else:
            blocker = "No valid static HTML entry point (e.g. index.html, public/index.html) found."
        return PreviewDetectResponse(
            status="UNSUPPORTED",
            category="unknown",
            entryPoint=None,
            previewUrl=None,
            totalAssets=0,
            detectedAssets=[],
            blockers=[blocker]
        )

    # 3. Detect valid static assets in repository
    valid_assets = [
        p for p in all_paths
        if os.path.splitext(p)[1].lower() in STATIC_MIME_TYPES
    ]

    return PreviewDetectResponse(
        status="READY",
        category="static",
        entryPoint=entry_point,
        previewUrl=f"/api/preview/{owner}/{repo_name}/{default_branch}/{entry_point}",
        totalAssets=len(valid_assets),
        detectedAssets=sorted(valid_assets)[:100],
        blockers=[],
    )


def sanitize_and_validate_path(file_path: str, tree_paths: Set[str]) -> str:
    """
    Enforce strict path validation and traversal prevention.
    Returns normalized relative path or raises HTTPException.
    """
    if not file_path or not isinstance(file_path, str):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    # Strip query parameters (?v=1) and fragments (#hash)
    raw_path = file_path.strip().split("?")[0].split("#")[0]
    if raw_path.startswith("/") or raw_path.startswith("\\"):
        raise HTTPException(status_code=400, detail="Absolute paths are not allowed.")

    # Decode URL-encoded characters (e.g. %20 -> space)
    decoded = urllib.parse.unquote(raw_path)

    # Clean path and prevent directory traversal
    clean_path = posixpath.normpath(decoded)

    if clean_path.startswith("..") or "/../" in f"/{clean_path}/" or clean_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Path traversal detected.")

    # Check extension and security blacklist
    base_name = posixpath.basename(clean_path).lower()
    ext = os.path.splitext(clean_path)[1].lower()

    if base_name.startswith(".env") or ext in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=403, detail="Access to sensitive or executable files is prohibited.")

    if ext not in STATIC_MIME_TYPES:
        raise HTTPException(status_code=403, detail=f"File extension '{ext}' is not supported for static preview.")

    # Verify that the path exists in the Git tree (direct match)
    if clean_path in tree_paths:
        return clean_path

    # Case-insensitive fallback match (e.g. styles.CSS vs styles.css)
    lower_map = {p.lower(): p for p in tree_paths}
    if clean_path.lower() in lower_map:
        return lower_map[clean_path.lower()]

    raise HTTPException(status_code=404, detail=f"File '{clean_path}' not found in repository.")

    return clean_path


def inject_base_tag_into_html(html_text: str, owner: str, repo: str, branch: str, file_path: str) -> str:
    """
    Inject a <base> tag into HTML so all relative CSS, JS, and image paths
    automatically resolve through the preview proxy.
    """
    entry_dir = posixpath.dirname(file_path)
    base_href = f"/api/preview/{owner}/{repo}/{branch}/{entry_dir}/" if entry_dir else f"/api/preview/{owner}/{repo}/{branch}/"

    base_tag = f'<base href="{base_href}">'

    # Case-insensitive insertion after <head>
    head_match = re.search(r"<head\b[^>]*>", html_text, re.IGNORECASE)
    if head_match:
        pos = head_match.end()
        return html_text[:pos] + "\n  " + base_tag + html_text[pos:]

    # Fallback: insertion after <html>
    html_match = re.search(r"<html\b[^>]*>", html_text, re.IGNORECASE)
    if html_match:
        pos = html_match.end()
        return html_text[:pos] + f"\n<head>\n  {base_tag}\n</head>" + html_text[pos:]

    # Fallback: prepend at top of document
    return f"<head>\n  {base_tag}\n</head>\n" + html_text
