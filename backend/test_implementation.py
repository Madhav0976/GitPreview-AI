#!/usr/bin/env python
"""
Test script to verify the repository metadata analysis implementation.
"""
import sys
sys.path.insert(0, '.')

import asyncio
from app.services.github_client import parse_repo_url, fetch_repo_metadata
from app.models import RepositoryMetadata, AnalysisResponse

async def test_github_api():
    """Test fetching real repository metadata from GitHub API."""
    print("=" * 60)
    print("Testing Repository Metadata Analysis Implementation")
    print("=" * 60)
    
    # Test with a well-known repository
    test_repos = [
        "https://github.com/torvalds/linux",
        "https://github.com/facebook/react",
    ]
    
    for repo_url in test_repos:
        print(f"\nTesting: {repo_url}")
        print("-" * 60)
        
        try:
            # Parse the URL
            owner, repo_name = parse_repo_url(repo_url)
            print(f"✓ URL parsed successfully: owner={owner}, repo={repo_name}")
            
            # Fetch metadata
            print("  Fetching metadata from GitHub API...")
            metadata_dict = await fetch_repo_metadata(repo_url)
            
            # Create RepositoryMetadata object
            metadata = RepositoryMetadata(**metadata_dict)
            
            # Display results
            print(f"  ✓ Repository: {metadata.name}")
            print(f"  ✓ Description: {metadata.description[:80]}..." if metadata.description else "  ✓ Description: None")
            print(f"  ✓ Stars: {metadata.stars}")
            print(f"  ✓ Forks: {metadata.forks}")
            print(f"  ✓ License: {metadata.license or 'Not specified'}")
            print(f"  ✓ Default Branch: {metadata.defaultBranch}")
            print(f"  ✓ Languages: {len(metadata.languages)} detected")
            if metadata.languages:
                top_langs = sorted(metadata.languages.items(), key=lambda x: x[1], reverse=True)[:3]
                for lang, bytes_count in top_langs:
                    print(f"     - {lang}: {bytes_count} bytes")
            
            # Create AnalysisResponse
            response = AnalysisResponse(metadata=metadata)
            print(f"  ✓ Response object created successfully")
            
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")

def test_url_parsing():
    """Test URL parsing with various formats."""
    print("\n" + "=" * 60)
    print("Testing URL Parsing")
    print("=" * 60)
    
    test_cases = [
        ("https://github.com/torvalds/linux", ("torvalds", "linux")),
        ("https://github.com/facebook/react.git", ("facebook", "react")),
        ("git@github.com:kubernetes/kubernetes.git", ("kubernetes", "kubernetes")),
        ("https://github.com/microsoft/vscode/", ("microsoft", "vscode")),
    ]
    
    for url, expected in test_cases:
        try:
            owner, repo = parse_repo_url(url)
            if (owner, repo) == expected:
                print(f"✓ {url}")
                print(f"  -> {owner}/{repo}")
            else:
                print(f"✗ {url}")
                print(f"  Expected: {expected[0]}/{expected[1]}, Got: {owner}/{repo}")
        except Exception as e:
            print(f"✗ {url}: {str(e)}")

if __name__ == "__main__":
    print("\nStarting tests...\n")
    
    # Run sync tests
    test_url_parsing()
    
    # Run async tests
    print("\n")
    asyncio.run(test_github_api())
    
    print("\n" + "=" * 60)
    print("Testing Complete!")
    print("=" * 60)
