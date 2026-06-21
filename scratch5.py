import asyncio
import httpx

async def main():
    url = "https://raw.githubusercontent.com/facebook/react/main/packages/react/package.json"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        print("Status:", r.status_code)
        if r.status_code == 200:
            data = r.json()
            print("Name:", data.get("name"))
            print("react in deps?", "react" in data.get("dependencies", {}))

if __name__ == "__main__":
    asyncio.run(main())
