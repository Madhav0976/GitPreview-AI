#!/usr/bin/env python
"""
Local technology detection tests (without GitHub API calls).
Tests the detection logic with sample file contents.
"""
import sys
sys.path.insert(0, '.')

from app.services.technology_detector import (
    detect_from_package_json,
    detect_from_requirements_txt,
    detect_from_pyproject_toml,
    detect_from_package_lock_json,
    detect_vite,
    detect_next_config,
    detect_django,
    detect_flask_or_fastapi,
    detect_python_framework,
)


def test_package_json_detection():
    """Test package.json detection."""
    print("\n" + "=" * 70)
    print("TEST: package.json Detection")
    print("=" * 70)
    
    # Test React project
    react_package = '''
    {
        "name": "my-react-app",
        "dependencies": {
            "react": "^18.0.0",
            "react-dom": "^18.0.0"
        },
        "devDependencies": {
            "typescript": "^5.0.0"
        }
    }
    '''
    
    result = detect_from_package_json(react_package)
    print(f"✓ React project: {sorted(list(result))}")
    assert "React" in result
    assert "TypeScript" in result
    assert "Node.js" in result
    
    # Test Next.js project
    nextjs_package = '''
    {
        "name": "my-nextjs-app",
        "dependencies": {
            "next": "^14.0.0",
            "react": "^18.0.0",
            "react-dom": "^18.0.0"
        }
    }
    '''
    
    result = detect_from_package_json(nextjs_package)
    print(f"✓ Next.js project: {sorted(list(result))}")
    assert "Next.js" in result
    assert "React" in result
    assert "Node.js" in result
    
    # Test Express backend
    express_package = '''
    {
        "name": "my-api",
        "dependencies": {
            "express": "^4.18.0"
        }
    }
    '''
    
    result = detect_from_package_json(express_package)
    print(f"✓ Express project: {sorted(list(result))}")
    assert "Express" in result
    assert "Node.js" in result
    
    print("✓ All package.json tests passed!")


def test_requirements_txt_detection():
    """Test requirements.txt detection."""
    print("\n" + "=" * 70)
    print("TEST: requirements.txt Detection")
    print("=" * 70)
    
    # Test Django project
    django_requirements = '''
    Django==4.2.0
    djangorestframework==3.14.0
    psycopg2-binary==2.9.0
    '''
    
    result = detect_from_requirements_txt(django_requirements)
    print(f"✓ Django project: {sorted(list(result))}")
    assert "Django" in result
    assert "Python" in result
    
    # Test FastAPI project
    fastapi_requirements = '''
    fastapi==0.100.0
    uvicorn==0.23.0
    pydantic==2.0.0
    '''
    
    result = detect_from_requirements_txt(fastapi_requirements)
    print(f"✓ FastAPI project: {sorted(list(result))}")
    assert "FastAPI" in result
    assert "Python" in result
    
    # Test Flask project
    flask_requirements = '''
    Flask==2.3.0
    Flask-SQLAlchemy==3.0.0
    '''
    
    result = detect_from_requirements_txt(flask_requirements)
    print(f"✓ Flask project: {sorted(list(result))}")
    assert "Flask" in result
    assert "Python" in result
    
    print("✓ All requirements.txt tests passed!")


def test_pyproject_toml_detection():
    """Test pyproject.toml detection."""
    print("\n" + "=" * 70)
    print("TEST: pyproject.toml Detection")
    print("=" * 70)
    
    # Test FastAPI project
    fastapi_pyproject = '''
    [tool.poetry.dependencies]
    python = "^3.9"
    fastapi = "^0.100.0"
    uvicorn = "^0.23.0"
    '''
    
    result = detect_from_pyproject_toml(fastapi_pyproject)
    print(f"✓ FastAPI (pyproject.toml): {sorted(list(result))}")
    assert "FastAPI" in result
    assert "Python" in result
    
    print("✓ All pyproject.toml tests passed!")


def test_vite_detection():
    """Test Vite detection."""
    print("\n" + "=" * 70)
    print("TEST: Vite Config Detection")
    print("=" * 70)
    
    vite_config = '''
    import { defineConfig } from 'vite'
    import react from '@vitejs/plugin-react'
    
    export default defineConfig({
        plugins: [react()],
    })
    '''
    
    result = detect_vite(vite_config)
    print(f"✓ Vite project: {sorted(list(result))}")
    assert "Vite" in result
    
    print("✓ Vite detection test passed!")


def test_next_config_detection():
    """Test Next.js config detection."""
    print("\n" + "=" * 70)
    print("TEST: Next.js Config Detection")
    print("=" * 70)
    
    next_config = '''
    /** @type {import('next').NextConfig} */
    const nextConfig = {
        reactStrictMode: true,
    }
    module.exports = nextConfig
    '''
    
    result = detect_next_config(next_config)
    print(f"✓ Next.js config: {sorted(list(result))}")
    assert "Next.js" in result
    assert "React" in result
    
    print("✓ Next.js config detection test passed!")


def test_django_management_detection():
    """Test Django manage.py detection."""
    print("\n" + "=" * 70)
    print("TEST: Django manage.py Detection")
    print("=" * 70)
    
    django_manage = '''
    #!/usr/bin/env python
    import os
    import sys
    from django.core.management import execute_from_command_line
    '''
    
    result = detect_django(django_manage)
    print(f"✓ Django project: {sorted(list(result))}")
    assert "Django" in result
    assert "Python" in result
    
    print("✓ Django detection test passed!")


def test_fastapi_app_detection():
    """Test FastAPI app.py detection."""
    print("\n" + "=" * 70)
    print("TEST: FastAPI app.py Detection")
    print("=" * 70)
    
    fastapi_app = '''
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    app = FastAPI()
    
    @app.get("/")
    def read_root():
        return {"Hello": "World"}
    '''
    
    result = detect_flask_or_fastapi(fastapi_app)
    print(f"✓ FastAPI app.py: {sorted(list(result))}")
    assert "FastAPI" in result
    assert "Python" in result
    
    print("✓ FastAPI app detection test passed!")


def main():
    """Run all tests."""
    print("\n" + "█" * 70)
    print("█ TECHNOLOGY DETECTION - LOCAL UNIT TESTS")
    print("█" * 70)
    
    try:
        test_package_json_detection()
        test_requirements_txt_detection()
        test_pyproject_toml_detection()
        test_vite_detection()
        test_next_config_detection()
        test_django_management_detection()
        test_fastapi_app_detection()
        
        print("\n" + "=" * 70)
        print("✓ ALL TESTS PASSED!")
        print("=" * 70 + "\n")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
