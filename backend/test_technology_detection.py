#!/usr/bin/env python
"""
Test script for technology detection with API token support.
Set GITHUB_TOKEN environment variable to increase rate limits:
export GITHUB_TOKEN=your_github_personal_access_token
"""
import sys
sys.path.insert(0, '.')

import asyncio
import os
from app.models import AnalyzeRequest
from app.api.analyze import analyze


async def test_technology_detection():
    """Test technology detection with real repositories."""
    print("\n" + "=" * 70)
    print("TECHNOLOGY DETECTION TEST")
    print("=" * 70)
    
    # Check if GitHub token is set
    if os.getenv("GITHUB_TOKEN"):
        print("✓ GITHUB_TOKEN is set (Rate limit: 5000/hour)")
    else:
        print("⚠ GITHUB_TOKEN not set (Rate limit: 60/hour)")
        print("  Set GITHUB_TOKEN environment variable for better performance")
    
    test_repos = [
        ("https://github.com/torvalds/linux", "Linux Kernel"),
        ("https://github.com/facebook/react", "React"),
        ("https://github.com/vercel/next.js", "Next.js"),
        ("https://github.com/microsoft/vscode", "VS Code"),
        ("https://github.com/Madhav0976/student-productivity-os", "Student Productivity OS"),
    ]
    
    results = []
    
    for repo_url, repo_name in test_repos:
        print(f"\n{'─' * 70}")
        print(f"📦 Testing: {repo_name}")
        print(f"   URL: {repo_url}")
        print(f"{'─' * 70}")
        
        try:
            request = AnalyzeRequest(repoUrl=repo_url)
            result = await analyze(request)
            
            metadata = result.metadata
            
            print(f"✓ Name: {metadata.name}")
            print(f"✓ Description: {metadata.description[:70]}..." if metadata.description else "✓ Description: None")
            print(f"✓ Stars: {metadata.stars:,}")
            print(f"✓ Forks: {metadata.forks:,}")
            print(f"✓ License: {metadata.license or 'Not specified'}")
            print(f"✓ Default Branch: {metadata.defaultBranch}")
            print(f"✓ Languages (GitHub API): {len(metadata.languages)} detected")
            print(f"✓ Technologies Detected: {metadata.technologies}")
            
            results.append({
                "name": repo_name,
                "status": "✓ PASSED",
                "technologies": metadata.technologies,
            })
            
        except Exception as e:
            error_msg = str(e)
            print(f"✗ Error: {error_msg[:100]}")
            results.append({
                "name": repo_name,
                "status": f"✗ FAILED: {error_msg[:50]}",
                "technologies": [],
            })
    
    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    
    passed = sum(1 for r in results if "PASSED" in r["status"])
    failed = len(results) - passed
    
    for result in results:
        status_icon = "✓" if "PASSED" in result["status"] else "✗"
        techs = ", ".join(result["technologies"]) if result["technologies"] else "None detected"
        print(f"{status_icon} {result['name']:<30} | {techs}")
    
    print(f"\n{'─' * 70}")
    print(f"Total: {passed} passed, {failed} failed")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(test_technology_detection())
