"""Health check script for the arbitrage bot."""

import json
import sys
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import sqlite3

    import pkg_resources
    from dotenv import load_dotenv

    # Connector imports
    from src.connectors.base import MockConnector
    from src.connectors.kalshi import KalshiConnector
    from src.connectors.polymarket import PolymarketConnector
    from src.core.backtest import BacktestEngine

    # Core imports
    from src.core.config import settings
    from src.core.discovery import DiscoveryEngine
    from src.core.execution import ExecutionEngine
    from src.core.fees import create_default_fee_calculator
    from src.core.health import HealthMonitor
    from src.core.live import LiveTradingEngine
    from src.core.matcher import EventMatcher
    from src.core.odds import calculate_arbitrage_edge
    from src.core.paper import PaperTradingEngine
    from src.core.persistence import PersistenceManager
    from src.core.portfolio import Portfolio
    from src.core.risk import RiskManager
    from src.core.sizing import PositionSizer
    from src.core.types import Venue

except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)


def check_python_version() -> dict[str, Any]:
    """Check Python version."""
    import sys
    version = sys.version_info

    return {
        "version": f"{version.major}.{version.minor}.{version.micro}",
        "ok": version >= (3, 11),
        "required": ">=3.11"
    }


def check_dependencies() -> dict[str, Any]:
    """Check installed dependencies."""
    required_packages = [
        "pydantic",
        "pydantic-settings",
        "httpx",
        "websockets",
        "sqlmodel",
        "structlog",
        "python-dotenv",
        "ruff",
        "mypy",
        "pytest",
        "hypothesis",
        "black",
    ]

    installed = {}
    missing = []

    for package in required_packages:
        try:
            dist = pkg_resources.get_distribution(package)
            installed[package] = dist.version
        except pkg_resources.DistributionNotFound:
            missing.append(package)

    return {
        "installed": installed,
        "missing": missing,
        "ok": len(missing) == 0
    }


def check_database() -> dict[str, Any]:
    """Check database connectivity."""
    try:
        # Try to create and connect to SQLite database
        db_path = "pm_arb.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Test basic operations
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        cursor.execute("INSERT INTO test (id) VALUES (1)")
        cursor.execute("SELECT * FROM test")
        result = cursor.fetchone()
        cursor.execute("DROP TABLE test")

        conn.close()

        return {
            "path": db_path,
            "ok": True,
            "error": None
        }
    except Exception as e:
        return {
            "path": "pm_arb.db",
            "ok": False,
            "error": str(e)
        }


def check_environment() -> dict[str, Any]:
    """Check environment configuration."""
    try:
        # Load .env file if it exists
        env_file = Path(".env")
        if env_file.exists():
            load_dotenv(env_file)

        # Check critical settings
        critical_settings = [
            "mode",
            "min_edge_bps",
            "max_open_risk_usd",
            "starting_balance_usd",
            "kelly_fraction",
        ]

        missing_settings = []
        for setting in critical_settings:
            if not hasattr(settings, setting):
                missing_settings.append(setting)

        return {
            "env_file_exists": env_file.exists(),
            "settings_loaded": True,
            "missing_critical": missing_settings,
            "ok": len(missing_settings) == 0
        }
    except Exception as e:
        return {
            "env_file_exists": False,
            "settings_loaded": False,
            "missing_critical": [],
            "ok": False,
            "error": str(e)
        }


def check_modules() -> dict[str, Any]:
    """Check if all core modules can be imported and instantiated."""
    module_tests = {}

    try:
        # Test core modules
        fee_calculator = create_default_fee_calculator()
        module_tests["fee_calculator"] = True

        event_matcher = EventMatcher()
        module_tests["event_matcher"] = True

        risk_limits = settings.get_risk_limits()
        position_sizer = PositionSizer(risk_limits)
        module_tests["position_sizer"] = True

        risk_manager = RiskManager(risk_limits)
        module_tests["risk_manager"] = True

        portfolio = Portfolio()
        module_tests["portfolio"] = True

        persistence = PersistenceManager("sqlite:///./pm_arb.db")
        module_tests["persistence"] = True

        # Test connectors
        mock_connector = MockConnector(Venue.POLYMARKET, {})
        module_tests["mock_connector"] = True

        # Test trading engines
        paper_engine = PaperTradingEngine()
        module_tests["paper_engine"] = True

        backtest_engine = BacktestEngine()
        module_tests["backtest_engine"] = True

        return {
            "modules": module_tests,
            "ok": all(module_tests.values())
        }
    except Exception as e:
        return {
            "modules": module_tests,
            "ok": False,
            "error": str(e)
        }


def check_health_monitor() -> dict[str, Any]:
    """Check health monitoring system."""
    try:
        health_monitor = HealthMonitor()

        # Test health endpoints (synchronous check)
        health_status = health_monitor.get_health_status()

        return {
            "health_monitor": True,
            "status": health_status.status,
            "ok": True
        }
    except Exception as e:
        return {
            "health_monitor": False,
            "ok": False,
            "error": str(e)
        }


def main():
    """Run complete health check."""
    print("Running PM Arbitrage Bot health check...")

    health_report = {
        "python": check_python_version(),
        "deps": check_dependencies(),
        "db": check_database(),
        "env": check_environment(),
        "modules": check_modules(),
        "health": check_health_monitor(),
    }

    # Overall health status
    overall_ok = all(
        health_report[key]["ok"]
        for key in ["python", "deps", "db", "env", "modules", "health"]
    )

    health_report["overall"] = {
        "ok": overall_ok,
        "status": "healthy" if overall_ok else "unhealthy"
    }

    # Print JSON output
    print(json.dumps(health_report, indent=2))

    # Exit with appropriate code
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
