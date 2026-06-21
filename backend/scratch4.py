import asyncio
from app.services.technology_detector import detect_technologies
from app.services.folder_analyzer import detect_folder_structure

async def test_repo(owner, name):
    print(f"\n--- Testing {owner}/{name} ---")
    techs = await detect_technologies(owner, name)
    print("Technologies:", sorted(list(techs)))
    folders = await detect_folder_structure(owner, name)
    print("Entry Points:", folders.get("entryPoints", []))

async def main():
    repos = [
        ("facebook", "react"),
        ("vercel", "next.js"),
        ("tiangolo", "fastapi"),
        ("pallets", "flask"),
    ]
    for owner, name in repos:
        await test_repo(owner, name)

if __name__ == "__main__":
    asyncio.run(main())
