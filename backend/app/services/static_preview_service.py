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
    ".pdf": "application/pdf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
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
    If package.json is present (frontend/SPA project), prioritize compiled output directories:
    1. dist/index.html
    2. build/index.html
    3. out/index.html
    4. root index.html
    5. root index.htm
    6. public/index.html
    For plain static sites:
    1. root index.html
    2. root index.htm
    3. public/index.html
    4. dist/index.html
    5. build/index.html
    6. one unambiguous root-level HTML file
    """
    path_map = {p.lower(): p for p in all_paths}
    has_pkg = any(p in path_map for p in ("package.json", "frontend/package.json"))

    if has_pkg and any(p in path_map for p in ("dist/index.html", "build/index.html", "out/index.html")):
        priority_candidates = [
            "dist/index.html",
            "build/index.html",
            "out/index.html",
            "index.html",
            "index.htm",
            "public/index.html",
        ]
    else:
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
    has_prebuilt_spa = any(p in all_paths for p in ("dist/index.html", "build/index.html", "out/index.html"))
    if not has_prebuilt_spa and ("package.json" in root_files or "frontend/package.json" in all_paths):
        pkg_path = "package.json" if "package.json" in root_files else "frontend/package.json"
        pkg_content = await fetch_file_content(owner, repo_name, pkg_path, client, default_branch)
        try:
            pkg_data = json.loads(pkg_content) if pkg_content else {}
            deps = pkg_data.get("dependencies") or {}
            dev_deps = pkg_data.get("devDependencies") or {}
            scripts = pkg_data.get("scripts") or {}
            all_deps = {**deps, **dev_deps}

            # Backend API check (Express, Nest)
            if "express" in all_deps or "@nestjs/core" in all_deps:
                return PreviewDetectResponse(
                    status="UNSUPPORTED",
                    category="backend API",
                    entryPoint=None,
                    previewUrl=None,
                    totalAssets=0,
                    detectedAssets=[],
                    blockers=["This repository requires a live Node.js server runtime (Express/NestJS) and cannot be previewed as a static site."]
                )

            # Check if it requires a build or framework runtime
            if any(sig in all_deps for sig in UNSUPPORTED_FRAMEWORK_SIGNATURES) or "build" in scripts:
                category = "frontend"
                if "next" in all_deps:
                    category = "full-stack"
                return PreviewDetectResponse(
                    status="UNSUPPORTED",
                    category=category,
                    entryPoint=None,
                    previewUrl=None,
                    totalAssets=0,
                    detectedAssets=[],
                    blockers=[f"This repository requires a client-side build step ({category}) before it can be rendered. No pre-built output directory (dist/ or build/) was found."]
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


class PreviewResolutionError(HTTPException):
    """
    HTTPException carrying rich diagnostic metadata for preview path failures.
    """
    def __init__(
        self,
        status_code: int,
        detail: str,
        requested_target: str,
        resolved_target: Optional[str] = None,
        repository_type: str = "static_html",
        reason: str = "",
        exists: bool = False,
        suggested_fix: str = "",
    ):
        self.requested_target = requested_target
        self.resolved_target = resolved_target
        self.repository_type = repository_type
        self.reason = reason or detail
        self.exists = exists
        self.suggested_fix = suggested_fix
        self.diagnostic = {
            "requestedTarget": requested_target,
            "resolvedTarget": resolved_target,
            "repositoryType": repository_type,
            "reason": self.reason,
            "exists": exists,
            "suggestedFix": suggested_fix,
        }
        super().__init__(status_code=status_code, detail=detail)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detail": self.detail,
            **self.diagnostic,
        }


def render_diagnostic_html(
    exc: PreviewResolutionError,
    owner: str,
    repo: str,
    branch: str,
    entry_url: Optional[str] = None,
) -> str:
    """
    Render a clean, modern HTML error card inside the preview iframe
    when an asset or navigation link fails to resolve.
    """
    import html as html_lib

    home_url = entry_url or f"/api/preview/{owner}/{repo}/{branch}/"
    safe_req = html_lib.escape(exc.requested_target or "unknown")
    safe_res = html_lib.escape(exc.resolved_target or "None")
    safe_type = html_lib.escape(exc.repository_type or "Static Website")
    safe_reason = html_lib.escape(exc.reason or exc.detail)
    safe_fix = html_lib.escape(exc.suggested_fix or "Check that the link target matches a file in the repository.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Preview Resolution Error - GitPreview AI</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #090d16;
      color: #f1f5f9;
      margin: 0;
      padding: 1.5rem;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 85vh;
      box-sizing: border-box;
    }}
    .card {{
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 1rem;
      padding: 1.75rem;
      max-width: 560px;
      width: 100%;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
    }}
    .header {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }}
    .icon {{
      width: 2.25rem;
      height: 2.25rem;
      border-radius: 9999px;
      background: rgba(239, 68, 68, 0.15);
      color: #ef4444;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
      font-weight: bold;
    }}
    h2 {{
      margin: 0;
      font-size: 1.15rem;
      font-weight: 600;
      color: #ffffff;
    }}
    .table {{
      background: #0b1120;
      border: 1px solid #1e293b;
      border-radius: 0.75rem;
      overflow: hidden;
      margin-bottom: 1.25rem;
      font-size: 0.825rem;
    }}
    .row {{
      display: flex;
      border-bottom: 1px solid #1e293b;
      padding: 0.65rem 0.85rem;
    }}
    .row:last-child {{
      border-bottom: none;
    }}
    .label {{
      width: 35%;
      color: #94a3b8;
      font-weight: 500;
    }}
    .value {{
      width: 65%;
      color: #e2e8f0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      word-break: break-all;
    }}
    .fix-box {{
      background: rgba(59, 130, 246, 0.08);
      border-left: 3px solid #3b82f6;
      border-radius: 0.375rem;
      padding: 0.75rem 0.85rem;
      font-size: 0.825rem;
      color: #93c5fd;
      line-height: 1.5;
      margin-bottom: 1.25rem;
    }}
    .actions {{
      display: flex;
      gap: 0.75rem;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #2563eb;
      color: #ffffff;
      text-decoration: none;
      font-size: 0.825rem;
      font-weight: 500;
      padding: 0.55rem 1rem;
      border-radius: 0.5rem;
      transition: background 0.15s;
    }}
    .btn:hover {{
      background: #1d4ed8;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="icon">!</div>
      <h2>Preview Resolution Error</h2>
    </div>
    <div class="table">
      <div class="row">
        <div class="label">Requested Target</div>
        <div class="value">{safe_req}</div>
      </div>
      <div class="row">
        <div class="label">Repository Type</div>
        <div class="value">{safe_type}</div>
      </div>
      <div class="row">
        <div class="label">Resolution Status</div>
        <div class="value">{safe_reason}</div>
      </div>
      <div class="row">
        <div class="label">Resolved Path</div>
        <div class="value">{safe_res}</div>
      </div>
    </div>
    <div class="fix-box">
      <strong>Suggested Fix:</strong> {safe_fix}
    </div>
    <div class="actions">
      <a href="{home_url}" class="btn">Back to Preview Entry Point</a>
    </div>
  </div>
</body>
</html>"""


def detect_is_spa_repository(tree_paths: Set[str]) -> bool:
    """
    Determine if the repository represents a Single Page Application (SPA)
    such as React, Vue, Vite, Next.js export, or has client-side routing.
    """
    lower_paths = {p.lower() for p in tree_paths}
    if any(p in lower_paths for p in ("dist/index.html", "build/index.html", "out/index.html")):
        return True

    spa_indicators = (
        "vite.config.js", "vite.config.ts", "vite.config.mjs",
        "next.config.js", "next.config.mjs", "next.config.ts",
        "angular.json", "vue.config.js", "svelte.config.js",
        "src/app.jsx", "src/app.tsx", "src/app.vue",
        "src/main.jsx", "src/main.tsx", "src/main.js", "src/main.ts",
        "src/index.jsx", "src/index.tsx", "src/index.js",
    )
    return any(ind in lower_paths for ind in spa_indicators)


def sanitize_and_validate_path(file_path: str, tree_paths: Set[str]) -> str:
    """
    Enforce strict path validation and traversal prevention.
    Returns normalized relative path or raises HTTPException.
    Maintains backward compatibility with unit tests.
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


def resolve_preview_target(
    file_path: str,
    tree_paths: Set[str],
    entry_point: Optional[str] = None,
    is_spa: bool = False,
) -> str:
    """
    Resolve requested preview path against the repository tree with complete navigation handling:
    1. Rejects unsafe schemes and directory traversal outside root.
    2. Resolves root/empty requests to the repository entrypoint.
    3. Handles relative static paths (about.html, pages/about.html, assets/image.png, resume.pdf).
    4. Handles extensionless SPA routes (/about, /projects) with fallback to index.html for SPAs.
    5. In static HTML repositories, reports missing file errors without blindly navigating.
    """
    repo_type = "spa_prebuilt" if is_spa else "static_html"

    if not isinstance(file_path, str):
        raise PreviewResolutionError(
            status_code=400,
            detail="Invalid file path type.",
            requested_target=str(file_path),
            repository_type=repo_type,
            reason="Path argument must be a valid string.",
            suggested_fix="Ensure file path is provided as a valid string.",
        )

    raw_stripped = file_path.strip()

    # Block unsafe protocol schemes
    lower_raw = raw_stripped.lower()
    if lower_raw.startswith(("javascript:", "file:", "vbscript:", "data:")):
        raise PreviewResolutionError(
            status_code=400,
            detail="Access to non-standard or unsafe URL schemes is prohibited.",
            requested_target=raw_stripped,
            repository_type=repo_type,
            reason=f"The scheme '{raw_stripped.split(':')[0]}:' is not permitted in preview URLs.",
            suggested_fix="Use standard relative repository paths or valid HTTPS links.",
        )

    # Clean query string (?v=1) and fragment (#about)
    path_no_query = raw_stripped.split("?")[0].split("#")[0]

    # Decode URL-encoded characters (%20 -> space)
    decoded = urllib.parse.unquote(path_no_query).strip()

    # Check for raw path traversal before stripping
    if decoded.startswith("..") or "/../" in f"/{decoded}/" or "\\.." in f"\\{decoded}\\":
        raise PreviewResolutionError(
            status_code=400,
            detail="Path traversal outside repository root is prohibited.",
            requested_target=file_path,
            repository_type=repo_type,
            reason="The path attempts to navigate above the repository root via '..' components.",
            suggested_fix="All links must resolve to files inside the repository.",
        )

    # Normalize posix path
    clean_path = posixpath.normpath(decoded.lstrip("/\\")) if decoded else ""

    if clean_path.startswith(".."):
        raise PreviewResolutionError(
            status_code=400,
            detail="Path traversal outside repository root is prohibited.",
            requested_target=file_path,
            repository_type=repo_type,
            reason="The path normalized to outside the repository root.",
            suggested_fix="Ensure relative paths stay inside the repository.",
        )

    # Root / empty / slash navigation
    if clean_path in ("", ".", "/"):
        resolved = entry_point or resolve_entry_point(tree_paths) or "index.html"
        return resolved

    # Check security blacklist (sensitive / server files)
    base_name = posixpath.basename(clean_path).lower()
    ext = posixpath.splitext(clean_path)[1].lower()

    if base_name.startswith(".env") or ext in BLOCKED_EXTENSIONS:
        raise PreviewResolutionError(
            status_code=403,
            detail="Access to sensitive or server-side executable files is prohibited.",
            requested_target=file_path,
            resolved_target=clean_path,
            repository_type=repo_type,
            reason=f"The file '{clean_path}' is protected by the preview security policy.",
            exists=(clean_path in tree_paths),
            suggested_fix="Static preview only serves safe frontend web assets (HTML, CSS, JS, images, fonts, PDF).",
        )

    lower_map = {p.lower(): p for p in tree_paths}

    # Direct tree existence check
    if clean_path in tree_paths:
        if ext and ext not in STATIC_MIME_TYPES:
            raise PreviewResolutionError(
                status_code=403,
                detail=f"File extension '{ext}' is not supported for static preview.",
                requested_target=file_path,
                resolved_target=clean_path,
                repository_type=repo_type,
                reason=f"File extension '{ext}' is not recognized as a supported static preview asset.",
                exists=True,
                suggested_fix="Static preview supports HTML, CSS, JS, images, fonts, PDF, and JSON.",
            )
        return clean_path

    # Case-insensitive direct tree check
    if clean_path.lower() in lower_map:
        matched = lower_map[clean_path.lower()]
        matched_ext = posixpath.splitext(matched)[1].lower()
        if matched_ext and matched_ext not in STATIC_MIME_TYPES:
            raise PreviewResolutionError(
                status_code=403,
                detail=f"File extension '{matched_ext}' is not supported for static preview.",
                requested_target=file_path,
                resolved_target=matched,
                repository_type=repo_type,
                reason=f"File extension '{matched_ext}' is not supported.",
                exists=True,
            )
        return matched

    # If entry point is in a subdirectory (dist/index.html or build/index.html),
    # check if path is relative to the entry directory
    if entry_point and "/" in entry_point:
        entry_dir = posixpath.dirname(entry_point)
        candidate = posixpath.normpath(f"{entry_dir}/{clean_path}")
        if candidate in tree_paths:
            return candidate
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]

    # Handle extensionless paths (Clean URLs & SPA Routes, e.g. /about, /projects)
    if not ext:
        # 1. Clean HTML file check: about -> about.html
        html_cand = f"{clean_path}.html"
        if html_cand in tree_paths:
            return html_cand
        if html_cand.lower() in lower_map:
            return lower_map[html_cand.lower()]

        # 2. Directory index check: about -> about/index.html
        dir_cand = f"{clean_path}/index.html"
        if dir_cand in tree_paths:
            return dir_cand
        if dir_cand.lower() in lower_map:
            return lower_map[dir_cand.lower()]

        # 3. Subdirectory clean match (e.g. pages/about.html)
        cand_base = f"{posixpath.basename(clean_path)}.html".lower()
        sub_cands = [p for p in tree_paths if posixpath.basename(p).lower() == cand_base]
        if len(sub_cands) == 1:
            return sub_cands[0]

        # 4. SPA route fallback
        if is_spa and entry_point and entry_point in tree_paths:
            return entry_point

        # 5. Non-SPA static HTML missing route
        raise PreviewResolutionError(
            status_code=404,
            detail=f"Route '/{clean_path}' not found in static repository.",
            requested_target=file_path,
            resolved_target=None,
            repository_type=repo_type,
            reason=f"Target '{clean_path}' could not be found as '{clean_path}.html' or '{clean_path}/index.html' in this static HTML repository.",
            exists=False,
            suggested_fix=f"Create '{clean_path}.html' or verify the navigation link href.",
        )

    # Uncompiled source file check (.tsx, .jsx, .ts, .vue)
    if ext in (".tsx", ".jsx", ".ts", ".vue", ".svelte"):
        raise PreviewResolutionError(
            status_code=403,
            detail=f"Uncompiled source file '{clean_path}' cannot be served directly.",
            requested_target=file_path,
            resolved_target=clean_path,
            repository_type=repo_type,
            reason=f"File '{clean_path}' is an uncompiled {ext} source file that requires a frontend bundler (Vite/Webpack).",
            exists=(clean_path in tree_paths or clean_path.lower() in lower_map),
            suggested_fix="Build the project ('npm run build') and ensure the compiled 'dist/' or 'build/' directory is committed.",
        )

    # Extension check
    if ext not in STATIC_MIME_TYPES:
        raise PreviewResolutionError(
            status_code=403,
            detail=f"File extension '{ext}' is not supported for static preview.",
            requested_target=file_path,
            resolved_target=clean_path,
            repository_type=repo_type,
            reason=f"File extension '{ext}' is not in the list of whitelisted web asset formats.",
            exists=(clean_path in tree_paths or clean_path.lower() in lower_map),
            suggested_fix="Static preview only serves web-safe formats (HTML, CSS, JS, images, fonts, PDF).",
        )

    # Subdirectory fallback for relative assets (e.g. assets/logo.png, resume.pdf)
    cand_base = posixpath.basename(clean_path).lower()
    sub_cands = [p for p in tree_paths if posixpath.basename(p).lower() == cand_base]
    if len(sub_cands) == 1:
        # For HTML files, if path differed, report missing file at requested location
        if ext in (".html", ".htm"):
            raise PreviewResolutionError(
                status_code=404,
                detail=f"File '{clean_path}' not found at requested path.",
                requested_target=file_path,
                resolved_target=sub_cands[0],
                repository_type=repo_type,
                reason=f"File '{clean_path}' could not be found at root, though '{sub_cands[0]}' exists in the repository.",
                exists=False,
                suggested_fix=f"Update link target in HTML to '{sub_cands[0]}'.",
            )
        # For media/document assets (PDFs, images, fonts), resolve to the discovered asset
        return sub_cands[0]

    # Target not found in repository
    raise PreviewResolutionError(
        status_code=404,
        detail=f"File '{clean_path}' not found in repository.",
        requested_target=file_path,
        resolved_target=None,
        repository_type=repo_type,
        reason=f"The requested file '{clean_path}' could not be found in the branch tree.",
        exists=False,
        suggested_fix="Verify the file is committed to the repository and the path is spelled correctly.",
    )


def classify_and_resolve_preview_url(
    raw_url: str,
    owner: str,
    repo: str,
    branch: str,
    tree_paths: Set[str],
    current_file: str = "index.html",
    is_spa: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Classify a requested preview navigation URL and resolve its target.
    Handles:
    - Hash links (#about, #projects)
    - External URLs (https://, mailto:, tel:)
    - Relative static paths (about.html, pages/about.html, assets/image.png, resume.pdf)
    - Absolute repository paths (/about.html, /assets/image.png)
    - SPA routes (/about, /projects, /contact)
    - Security traversal guards
    """
    if is_spa is None:
        is_spa = detect_is_spa_repository(tree_paths)

    repo_type = "spa_prebuilt" if is_spa else "static_html"
    clean_url = (raw_url or "").strip()

    # A. Hash links & Current Page Hash Navigation
    hash_idx = clean_url.find("#")
    if hash_idx != -1:
        path_part = clean_url[:hash_idx]
        hash_part = clean_url[hash_idx:]
        norm_path = path_part.lstrip("./\\").strip("/")
        current_base = posixpath.basename(current_file)
        if norm_path in ("", ".", current_file, current_base, "index.html", "index.htm"):
            return {
                "type": "hash",
                "kind": "hash",
                "allowed": True,
                "action": "scroll_in_page",
                "target": current_file,
                "requestedTarget": clean_url,
                "resolvedTarget": f"{current_file}{hash_part}",
                "exists": True,
                "repositoryType": repo_type,
            }

    if clean_url in ("#", "#top"):
        return {
            "type": "hash",
            "kind": "hash",
            "allowed": True,
            "action": "scroll_in_page",
            "target": current_file,
            "requestedTarget": clean_url,
            "resolvedTarget": f"{current_file}#",
            "exists": True,
            "repositoryType": repo_type,
        }

    # D. External URLs
    lower_url = clean_url.lower()
    if re.match(r"^(https?://|mailto:|tel:)", lower_url):
        return {
            "type": "external",
            "kind": "external",
            "allowed": True,
            "action": "open_external",
            "target": clean_url,
            "requestedTarget": clean_url,
            "resolvedTarget": clean_url,
            "exists": True,
            "repositoryType": repo_type,
        }

    # B / C / E: Resolve through preview target resolver
    if not clean_url.startswith("/") and not clean_url.startswith(".."):
        current_dir = posixpath.dirname(current_file)
        target_path = f"{current_dir}/{clean_url}" if current_dir else clean_url
    else:
        target_path = clean_url

    resolved_path = resolve_preview_target(
        target_path,
        tree_paths=tree_paths,
        entry_point=current_file,
        is_spa=is_spa,
    )

    req_ext = posixpath.splitext(clean_url.split("?")[0])[1].lower()
    kind = "spa_route" if (is_spa and resolved_path == current_file and not req_ext) else "static_asset"

    return {
        "type": kind,
        "kind": kind,
        "allowed": True,
        "action": "navigate_preview",
        "target": resolved_path,
        "requestedTarget": clean_url,
        "resolvedTarget": resolved_path,
        "previewUrl": f"/api/preview/{owner}/{repo}/{branch}/{resolved_path}",
        "exists": True,
        "repositoryType": repo_type,
    }


def rewrite_css_urls(css_text: str, owner: str, repo: str, branch: str, file_path: str = "") -> str:
    """
    Rewrite root-relative url('/...') references in CSS files
    to resolve against the preview proxy path.
    """
    entry_dir = posixpath.dirname(file_path) if file_path else ""
    base_href = f"/api/preview/{owner}/{repo}/{branch}/{entry_dir}/" if entry_dir else f"/api/preview/{owner}/{repo}/{branch}/"

    def _replace_url(match: re.Match) -> str:
        url_val = match.group(1).strip("'\"")
        if url_val.startswith("/") and not url_val.startswith("//") and not url_val.startswith("/api/preview/"):
            rewritten = f"{base_href}{url_val.lstrip('/')}"
            return f"url('{rewritten}')"
        return match.group(0)

    return re.sub(r'url\(\s*([\'"]?/[^\'")]+[\'"]?)\s*\)', _replace_url, css_text)


def inject_base_tag_into_html(html_text: str, owner: str, repo: str, branch: str, file_path: str) -> str:
    """
    Inject a <base> tag, rewrite root-relative HTML attributes, and inject
    the comprehensive client-side navigation resolution script.
    Ensures that hash navigation, external links, absolute paths, button clicks,
    form submissions, location assignments, and SPA routing stay within the preview namespace.
    """
    entry_dir = posixpath.dirname(file_path) if file_path else ""
    base_href = f"/api/preview/{owner}/{repo}/{branch}/{entry_dir}/" if entry_dir else f"/api/preview/{owner}/{repo}/{branch}/"
    repo_root_href = f"/api/preview/{owner}/{repo}/{branch}/"

    base_tag = f'<base href="{base_href}">'

    # 1. Rewrite root-relative HTML attributes (/about.html -> {repo_root_href}about.html)
    def _rewrite_root_attr(match: re.Match) -> str:
        attr_name = match.group(1)
        quote_char = match.group(2)
        attr_val = match.group(3)
        if attr_val.startswith("//") or attr_val.startswith("/api/preview/"):
            return match.group(0)
        stripped_val = attr_val.lstrip("/")
        return f"{attr_name}={quote_char}{repo_root_href}{stripped_val}{quote_char}"

    processed_html = re.sub(
        r'\b(href|src|action|poster|data-href|data-target)\s*=\s*(["\'])(/[^"\']*)\2',
        _rewrite_root_attr,
        html_text,
        flags=re.IGNORECASE,
    )

    # 2. Comprehensive client-side preview navigation script
    nav_script = f"""<script id="__gitpreview_nav_layer">
(function() {{
  var baseHref = "{base_href}";
  if (!baseHref.endsWith('/')) baseHref += '/';
  var repoRootHref = "{repo_root_href}";
  if (!repoRootHref.endsWith('/')) repoRootHref += '/';
  var currentFile = "{file_path}";
  var currentFileBase = currentFile.split('/').pop() || "index.html";

  // Centralized URL Resolver for sandboxed preview
  function resolveNavUrl(rawUrl) {{
    if (!rawUrl || typeof rawUrl !== 'string') return null;
    var s = rawUrl.trim();
    if (!s || s === 'javascript:void(0)' || s === 'javascript:;' || s === 'javascript:void(0);') {{
      return {{ type: 'noop' }};
    }}

    // 1. External protocols (http, https, mailto, tel, sms, etc.)
    if (/^(https?:|mailto:|tel:|sms:)/i.test(s)) {{
      return {{ type: 'external', url: s }};
    }}

    // 2. Hash & Same-Page Section Navigation
    // Examples:
    // "#about", "#", "#top",
    // "./#about", "./#projects",
    // "./index.html#about", "index.html#about",
    // "/#about", "/index.html#about"
    var hashIdx = s.indexOf('#');
    if (hashIdx !== -1) {{
      var pathPart = s.slice(0, hashIdx);
      var hashPart = s.slice(hashIdx);
      var cleanPath = pathPart.replace(/^\\.\\//, '').replace(/^\\/+/, '');
      if (cleanPath.startsWith(repoRootHref.replace(/^\\/+/, ''))) {{
        cleanPath = cleanPath.slice(repoRootHref.replace(/^\\/+/, '').length);
      }}
      if (cleanPath.startsWith(baseHref.replace(/^\\/+/, ''))) {{
        cleanPath = cleanPath.slice(baseHref.replace(/^\\/+/, '').length);
      }}
      cleanPath = cleanPath.replace(/^\\/+/, '');

      var isSamePage = (
        cleanPath === '' ||
        cleanPath === '.' ||
        cleanPath === currentFile ||
        cleanPath === currentFileBase ||
        cleanPath === 'index.html' ||
        cleanPath === 'index.htm'
      );

      if (isSamePage) {{
        return {{
          type: 'hash',
          hash: hashPart,
          targetId: hashPart.slice(1)
        }};
      }}
    }}

    // Back to top or empty root shortcuts
    if (s === '#' || s === '#top') {{
      return {{ type: 'hash', hash: '#', targetId: '' }};
    }}

    // 3. Internal preview paths
    // A. Root-relative paths: "/about.html", "/projects", "/assets/logo.png"
    if (s.startsWith('/') && !s.startsWith('/api/preview/')) {{
      var sub = s.replace(/^\\/+/, '');
      return {{
        type: 'internal',
        url: repoRootHref + sub
      }};
    }}

    // B. Full preview paths already resolved
    if (s.startsWith('/api/preview/')) {{
      return {{ type: 'internal', url: s }};
    }}

    // C. Relative paths: "about.html", "./about.html", "../about.html", "project-1.html"
    var cleanRel = s.replace(/^\\.\\//, '');
    return {{
      type: 'internal',
      url: baseHref + cleanRel
    }};
  }}

  // Smooth scroll helper for hash targets
  function scrollToTarget(targetId) {{
    if (!targetId || targetId === 'top') {{
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
      try {{ history.replaceState(null, '', baseHref + (targetId ? '#' + targetId : '#')); }} catch (e) {{}}
      return true;
    }}

    var el = document.getElementById(targetId);
    if (!el && window.CSS && CSS.escape) {{
      try {{ el = document.querySelector('#' + CSS.escape(targetId)); }} catch (e) {{}}
    }}
    if (!el) {{
      var named = document.getElementsByName(targetId);
      if (named && named.length > 0) el = named[0];
    }}
    if (!el) {{
      var all = document.querySelectorAll('section, div, a, h1, h2, h3, h4, h5, h6');
      for (var i = 0; i < all.length; i++) {{
        var aId = all[i].getAttribute('id') || all[i].getAttribute('name');
        if (aId && aId.toLowerCase() === targetId.toLowerCase()) {{
          el = all[i];
          break;
        }}
      }}
    }}

    if (el) {{
      el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      try {{ history.replaceState(null, '', baseHref + '#' + targetId); }} catch (e) {{}}
      return true;
    }}
    return false;
  }}

  // 1. Capture Click Events across all interactive elements (A, BUTTON, onclick, data-href)
  document.addEventListener('click', function(e) {{
    var el = e.target;
    while (el && el !== document.body && el !== document.documentElement) {{
      var tag = el.tagName ? el.tagName.toUpperCase() : '';
      if (tag === 'A' || tag === 'BUTTON' || el.hasAttribute('href') || el.hasAttribute('data-href')) {{
        break;
      }}
      el = el.parentElement;
    }}
    if (!el) return;

    var href = el.getAttribute('href') || el.getAttribute('data-href');

    // If button or element has no href, check onclick for location assignment
    if (!href && el.getAttribute('onclick')) {{
      var onclickCode = el.getAttribute('onclick');
      var m = onclickCode.match(/(?:location(?:\\.href)?|location\\.assign|location\\.replace)\\s*=\\s*['"]([^'"]+)['"]/);
      if (!m) {{
        m = onclickCode.match(/(?:location\\.assign|location\\.replace)\\(\\s*['"]([^'"]+)['"]\\s*\\)/);
      }}
      if (m && m[1]) {{
        href = m[1];
      }}
    }}

    if (!href) return;

    var res = resolveNavUrl(href);
    if (!res) return;

    if (res.type === 'noop') {{
      e.preventDefault();
      return;
    }}

    if (res.type === 'hash') {{
      e.preventDefault();
      e.stopPropagation();
      scrollToTarget(res.targetId);
      return;
    }}

    if (res.type === 'external') {{
      e.preventDefault();
      e.stopPropagation();
      window.open(res.url, '_blank', 'noopener,noreferrer');
      return;
    }}

    if (res.type === 'internal') {{
      var isBlank = el.getAttribute('target') === '_blank';
      var isDownload = el.hasAttribute('download');

      if (isBlank || isDownload) {{
        el.setAttribute('href', res.url);
        return;
      }}

      e.preventDefault();
      e.stopPropagation();
      window.location.href = res.url;
      return;
    }}
  }}, true);

  // 2. Capture Form Submissions
  document.addEventListener('submit', function(e) {{
    var form = e.target;
    if (!form || !form.getAttribute) return;
    var action = form.getAttribute('action');
    if (action) {{
      var res = resolveNavUrl(action);
      if (res && res.type === 'internal') {{
        form.setAttribute('action', res.url);
      }} else if (res && res.type === 'external') {{
        form.setAttribute('target', '_blank');
      }}
    }}
  }}, true);

  // 3. Patch Location Navigation API (assign, replace)
  try {{
    var origAssign = window.Location && Location.prototype && Location.prototype.assign
      ? Location.prototype.assign
      : window.location.assign;
    if (origAssign) {{
      var customAssign = function(url) {{
        var res = resolveNavUrl(url);
        if (res && res.type === 'hash') {{
          scrollToTarget(res.targetId);
          return;
        }}
        if (res && res.type === 'external') {{
          window.open(res.url, '_blank', 'noopener,noreferrer');
          return;
        }}
        var targetUrl = (res && res.url) ? res.url : url;
        return origAssign.call(window.location, targetUrl);
      }};
      try {{ window.location.assign = customAssign; }} catch (e) {{}}
      try {{ Location.prototype.assign = customAssign; }} catch (e) {{}}
    }}
  }} catch (e) {{}}

  try {{
    var origReplace = window.Location && Location.prototype && Location.prototype.replace
      ? Location.prototype.replace
      : window.location.replace;
    if (origReplace) {{
      var customReplace = function(url) {{
        var res = resolveNavUrl(url);
        if (res && res.type === 'hash') {{
          scrollToTarget(res.targetId);
          return;
        }}
        if (res && res.type === 'external') {{
          window.open(res.url, '_blank', 'noopener,noreferrer');
          return;
        }}
        var targetUrl = (res && res.url) ? res.url : url;
        return origReplace.call(window.location, targetUrl);
      }};
      try {{ window.location.replace = customReplace; }} catch (e) {{}}
      try {{ Location.prototype.replace = customReplace; }} catch (e) {{}}
    }}
  }} catch (e) {{}}

  // 4. Patch Location.prototype.href setter if supported
  try {{
    var locProto = window.Location ? Location.prototype : Object.getPrototypeOf(window.location);
    if (locProto) {{
      var hrefDesc = Object.getOwnPropertyDescriptor(locProto, 'href');
      if (hrefDesc && hrefDesc.set) {{
        var origSet = hrefDesc.set;
        Object.defineProperty(locProto, 'href', {{
          set: function(val) {{
            var res = resolveNavUrl(val);
            if (res && res.type === 'hash') {{
              scrollToTarget(res.targetId);
              return;
            }}
            if (res && res.type === 'external') {{
              window.open(res.url, '_blank', 'noopener,noreferrer');
              return;
            }}
            var targetVal = (res && res.url) ? res.url : val;
            origSet.call(this, targetVal);
          }},
          get: hrefDesc.get,
          configurable: true,
          enumerable: true
        }});
      }}
    }}
  }} catch (e) {{}}

  // 5. Patch History API for SPA Routers
  try {{
    var origPushState = history.pushState;
    history.pushState = function(state, title, url) {{
      if (typeof url === 'string') {{
        var res = resolveNavUrl(url);
        if (res && res.type === 'internal') {{
          url = res.url;
        }}
      }}
      return origPushState.call(this, state, title, url);
    }};

    var origReplaceState = history.replaceState;
    history.replaceState = function(state, title, url) {{
      if (typeof url === 'string') {{
        var res = resolveNavUrl(url);
        if (res && res.type === 'internal') {{
          url = res.url;
        }}
      }}
      return origReplaceState.call(this, state, title, url);
    }};
  }} catch (e) {{}}

  // Expose resolver for embedded scripts or testing
  window.__gitpreview_resolve_nav_url = resolveNavUrl;
  window.__gitpreview_scroll_to_target = scrollToTarget;
}})();
</script>"""

    injection_block = f"\n  {base_tag}\n  {nav_script}\n"

    # Insertion after <head>
    head_match = re.search(r"<head\b[^>]*>", processed_html, re.IGNORECASE)
    if head_match:
        pos = head_match.end()
        return processed_html[:pos] + injection_block + processed_html[pos:]

    # Fallback: insertion after <html>
    html_match = re.search(r"<html\b[^>]*>", processed_html, re.IGNORECASE)
    if html_match:
        pos = html_match.end()
        return processed_html[:pos] + f"\n<head>{injection_block}</head>" + processed_html[pos:]

    # Fallback: prepend at top of document
    return f"<head>{injection_block}</head>\n" + processed_html
