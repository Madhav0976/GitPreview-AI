import asyncio
from app.services.technology_detector import detect_technologies
from app.services.folder_analyzer import detect_folder_structure

async def main():
    print("Testing facebook/react...")
    techs = await detect_technologies("facebook", "react")
    print("React Techs:", techs)
    folders = await detect_folder_structure("facebook", "react")
    print("React Folders:", folders)
    
    print("\nTesting vercel/next.js...")
    techs2 = await detect_technologies("vercel", "next.js")
    print("Next.js Techs:", techs2)

if __name__ == "__main__":
    asyncio.run(main())
