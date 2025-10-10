#!/usr/bin/env python3
"""Health check script for PM Arbitrage Bot."""

import json
import sys
from pathlib import Path
from typing import Any, Dict

def check_python_version() -> Dict[str, Any]:
    """Check Python version."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    
    if version.major >= 3 and version.minor >= 11:
        return {"python": "ok", "version": version_str}
    else:
        return {
            "python": "error", 
            "version": version_str, 
            "message": f"Python 3.11+ required, found {version_str}"
        }

def check_env_file() -> Dict[str, Any]:
    """Check if .env file exists and is loadable."""
    env_file = Path(".env")
    
    if not env_file.exists():
        return {
            "env": "warning",
            "message": ".env file not found - using defaults"
        }
    
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        return {"env": "ok", "path": str(env_file)}
    except ImportError:
        return {
            "env": "warning",
            "message": "python-dotenv not installed - cannot load .env"
        }
    except Exception as e:
        return {
            "env": "error",
            "message": f"Failed to load .env: {str(e)}"
        }

def check_modules() -> Dict[str, Any]:
    """Check if core modules can be imported."""
    try:
        # Add src to path
        src_path = Path(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        
        # Try importing core modules
        from core.config import settings
        module_tests = {"config": "ok"}
        
        try:
            from core.health import HealthMonitor
            module_tests["health"] = "ok"
        except ImportError:
            module_tests["health"] = "not_found"
        
        try:
            from core.types import Venue
            module_tests["types"] = "ok"
        except ImportError:
            module_tests["types"] = "not_found"
        
        try:
            from core.matcher import EventMatcher
            module_tests["matcher"] = "ok"
        except ImportError:
            module_tests["matcher"] = "not_found"
        
        return {"modules": "ok", "details": module_tests}
        
    except ImportError as e:
        return {
            "modules": "error",
            "message": f"Failed to import core modules: {str(e)}"
        }
    except Exception as e:
        return {
            "modules": "error", 
            "message": f"Unexpected error: {str(e)}"
        }

def check_database() -> Dict[str, Any]:
    """Check database connectivity."""
    try:
        # Add src to path
        src_path = Path(__file__).parent.parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        
        from core.config import settings
        
        db_url = getattr(settings, 'DATABASE_URL', 'sqlite:///./pm_arb.db')
        
        if db_url.startswith('sqlite'):
            # Extract file path from SQLite URL
            db_path = db_url.replace('sqlite:///', '')
            if db_path.startswith('/'):
                db_file = Path(db_path)
            else:
                db_file = Path(db_path)
            
            if db_file.exists():
                return {"db": "ok", "path": str(db_file), "type": "sqlite"}
            else:
                return {
                    "db": "warning",
                    "message": f"SQLite file not found at {db_file}",
                    "type": "sqlite"
                }
        else:
            return {"db": "ok", "type": "other", "url": db_url}
            
    except Exception as e:
        return {
            "db": "error",
            "message": f"Database check failed: {str(e)}"
        }

def main() -> None:
    """Run complete health check."""
    print("Running PM Arbitrage Bot health check...")
    
    health_report = {
        "python": check_python_version(),
        "env": check_env_file(),
        "modules": check_modules(),
        "db": check_database(),
    }
    
    # Print JSON output
    print(json.dumps(health_report, indent=2))
    
    # Exit with appropriate code
    python_ok = health_report["python"].get("python") == "ok"
    env_ok = health_report["env"].get("env") in ["ok", "warning"]
    modules_ok = health_report["modules"].get("modules") == "ok"
    db_ok = health_report["db"].get("db") in ["ok", "warning"]
    
    overall_ok = python_ok and env_ok and modules_ok and db_ok
    
    sys.exit(0 if overall_ok else 1)

if __name__ == "__main__":
    main()
