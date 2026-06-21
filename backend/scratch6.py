from app.services.folder_analyzer import detect_entry_points

# Mock data for facebook/react root
root_names = [
    "package.json", "README.md", "fixtures", "packages", "scripts", 
    ".gitignore", "yarn.lock"
]
src_names = []

entry_points = detect_entry_points(root_names, src_names)
print("Facebook/React entry points:", entry_points)

# Mock data for some other app with no obvious entry
root_names2 = ["docs", "tests", "random_file.py", "Makefile"]
print("Other app entry points:", detect_entry_points(root_names2, []))

# Mock data for app with a weird readme
root_names3 = ["ReadMe", "src", "stuff"]
print("App 3 entry points:", detect_entry_points(root_names3, []))

