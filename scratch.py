import asyncio
import os
import json
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # Check facebook/react package.json
        url = "https://api.github.com/repos/facebook/react/contents/package.json"
        headers = {"Accept": "application/vnd.github.v3.raw"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            print("react in deps?", "react" in deps)
            print("react in devDeps?", "react" in dev_deps)
            print("name is react?", data.get("name") == "react")

        url2 = "https://api.github.com/repos/pallets/flask/contents/setup.py"
        # wait, let's just see pyproject.toml
        url_pyproject = "https://api.github.com/repos/pallets/flask/contents/pyproject.toml"
        response2 = await client.get(url_pyproject, headers=headers)
        if response2.status_code == 200:
            print("Flask pyproject.toml exists.")
            
if __name__ == "__main__":
    asyncio.run(main())
