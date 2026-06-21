from app.services.technology_detector import detect_from_package_json, detect_from_package_lock_json

# Test React monorepo detection
package_json_react = '{"private": true, "name": "react", "dependencies": {}}'
print("React tech:", detect_from_package_json(package_json_react))

# Test Next.js monorepo detection
package_json_next = '{"name": "next", "devDependencies": {"typescript": "5.0.0"}}'
print("Next.js tech:", detect_from_package_json(package_json_next))

# Test Vite monorepo detection
package_json_vite = '{"name": "vite"}'
print("Vite tech:", detect_from_package_json(package_json_vite))

# Test missing deps gracefully
package_json_broken = '{"name": "broken"}'
print("Broken tech:", detect_from_package_json(package_json_broken))

