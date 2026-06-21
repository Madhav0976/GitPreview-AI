import asyncio
import os
import json
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        url = "https://api.github.com/repos/facebook/react/contents/package.json"
        headers = {"Accept": "application/vnd.github.v3.raw"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        response = await client.get(url, headers=headers)
        print("Status:", response.status_code)
        if response.status_code == 200:
            try:
                data = response.json()
                deps = data.get("dependencies", {}) or {}
                dev_deps = data.get("devDependencies", {}) or {}
                print("react in deps?", "react" in deps)
                print("react in devDeps?", "react" in dev_deps)
                print("name:", data.get("name"))
                
                # Let's print keys in dependencies and devDependencies
                print("dep keys:", list(deps.keys())[:5])
                print("devDep keys:", list(dev_deps.keys())[:5])
            except Exception as e:
                print("Error parsing json:", e)
                
if __name__ == "__main__":
    asyncio.run(main())
