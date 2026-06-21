# Technology Detection Feature

## Overview

The technology detection feature automatically identifies:
- **Frontend Frameworks**: React, Next.js, Vue, Angular, Vite
- **Backend Frameworks**: Node.js, Express, FastAPI, Flask, Django
- **Programming Languages**: JavaScript, TypeScript, Python, Java, C++, Go

## How It Works

### Detection Pipeline
1. **Repository Metadata Fetch** - Gets repo info from GitHub API
2. **File Analysis** - Fetches key configuration files from GitHub
3. **Pattern Matching** - Analyzes file contents for framework signatures
4. **Technology List** - Returns sorted list of detected technologies

### Detection Files
The system checks for and analyzes these files:
```
package.json          → Detects React, Vue, Angular, Vite, Express, TypeScript
package-lock.json     → Secondary Node.js detection
requirements.txt      → Detects FastAPI, Flask, Django
pyproject.toml        → Detects Python frameworks
vite.config.ts/js     → Detects Vite
next.config.js/mjs    → Detects Next.js, React
manage.py             → Detects Django
app.py                → Detects Flask, FastAPI
main.py               → Detects Python frameworks
```

## Usage

### Basic API Call
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repoUrl": "https://github.com/facebook/react"}'
```

### Example Response
```json
{
  "metadata": {
    "owner": "facebook",
    "name": "react",
    "description": "The library for web and native user interfaces.",
    "stars": 245968,
    "forks": 51077,
    "license": "MIT License",
    "defaultBranch": "main",
    "languages": {
      "JavaScript": 5592744,
      "Rust": 2957666,
      "TypeScript": 2563814
    },
    "technologies": ["JavaScript", "Node.js", "React", "TypeScript"]
  }
}
```

## Rate Limit Handling

### Without GitHub Token
- **Rate Limit**: 60 requests/hour
- **Issue**: May be exceeded when analyzing multiple repositories
- **Solution**: Set GitHub token for higher limits

### With GitHub Token (Recommended)
- **Rate Limit**: 5000 requests/hour
- **Setup**: 
  ```bash
  export GITHUB_TOKEN=your_github_personal_access_token
  ```

### Getting a GitHub Personal Access Token
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Select scopes: `repo:read`
4. Copy the token and set it in your environment:
   ```bash
   export GITHUB_TOKEN=ghp_xxxxxxxxxxxxx
   ```

## Testing

### Local Unit Tests (No API Calls)
Run tests that verify detection logic with sample files:
```bash
python test_technology_detection_local.py
```

Tests included:
- package.json detection (React, Next.js, Express)
- requirements.txt detection (Django, FastAPI, Flask)
- pyproject.toml detection (FastAPI)
- Config file detection (Vite, Next.js)
- manage.py and app.py detection

### Integration Tests (Requires API Access)
```bash
python test_technology_detection.py
```

Tests against real repositories:
- facebook/react
- vercel/next.js
- microsoft/vscode
- Madhav0976/student-productivity-os
- torvalds/linux

## Detected Technologies Examples

### JavaScript/Node.js Projects
- **React**: Detected from `package.json` with "react" dependency
- **Next.js**: Detected from `next.config.js` or "next" dependency
- **Vue**: Detected from "vue" dependency
- **Angular**: Detected from "@angular/core" dependency
- **Vite**: Detected from `vite.config.ts/js` or "vite" dependency
- **Express**: Detected from "express" dependency
- **TypeScript**: Detected from "typescript" in devDependencies

### Python Projects
- **Django**: Detected from `manage.py`, `requirements.txt`, or "django" in `pyproject.toml`
- **FastAPI**: Detected from "fastapi" in `requirements.txt` or `pyproject.toml`
- **Flask**: Detected from "flask" in `requirements.txt` or `app.py`

## Limitations

### Current Scope
- Only analyzes files at repository root or first level
- Reads file contents up to 1MB
- Supports UTF-8 encoded files
- Requires files to exist in repository default branch

### Not Implemented
- Language detection from source code analysis
- Monorepo structure detection
- Nested framework detection
- Custom framework detection
- Version information extraction

## Architecture

### Files
```
backend/
├── app/
│   ├── models.py                    # Data models with technologies field
│   ├── services/
│   │   ├── github_client.py         # GitHub API integration
│   │   └── technology_detector.py   # Technology detection logic
│   └── api/
│       └── analyze.py               # API endpoint
└── test_technology_detection_local.py  # Unit tests
```

### Module Responsibilities
- `github_client.py`: Orchestrates metadata + technology detection
- `technology_detector.py`: Fetches files and analyzes content
- `models.py`: Defines response schema with technologies
- `analyze.py`: HTTP endpoint handling and error management

## Performance

### API Call Timings (with token)
- Repository metadata: ~200ms
- File fetching (8-10 files): ~800ms
- Total per repository: ~1-1.5 seconds

### Rate Limit Consumption
- Per repository analysis: ~15 API calls
  - 1 for repository info
  - 1 for languages
  - ~13 for file content checks
- With token: 5000/15 = ~333 repositories before rate limit

## Troubleshooting

### Issue: Rate limit exceeded
```
Error: 403 rate limit exceeded
```
**Solution**: Set GITHUB_TOKEN environment variable

### Issue: Repository not found
```
Error: Client error '404 Repository Not Found'
```
**Solution**: Verify the repository URL is correct and public

### Issue: Timeout
```
Error: Read timed out
```
**Solution**: Network issue or GitHub API overloaded. Retry after a few seconds.

### Issue: No technologies detected
```
"technologies": []
```
**Possible causes**:
- Repository doesn't have analyzed files at root level
- Custom framework not in detection list
- Binary/compiled language without config files
- Solution: Check repository structure and add custom detection if needed

## Future Enhancements

Possible improvements:
1. Add support for more languages (C++, Java, Go)
2. Scan nested directories for config files
3. Analyze source code imports for framework detection
4. Extract version information from lock files
5. Support private repositories with per-user tokens
6. Add caching to reduce API calls
7. Batch repository analysis
8. Custom detection patterns
