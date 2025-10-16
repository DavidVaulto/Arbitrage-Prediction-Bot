#!/usr/bin/env python3
"""CLI tool for managing event mappings and overrides.

This tool allows you to:
- Review unmapped markets
- Add manual overrides
- View mapping statistics
- Export/import mappings
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.event_registry import CanonicalEvent, EventRegistry, EventScope, EventType, VenueMapping
from src.core.venue_mappers import KalshiMapper, PolymarketMapper


def setup_registry(events_file: str | None = None, mappings_file: str | None = None) -> EventRegistry:
    """Setup event registry with default or custom files."""
    if not events_file:
        events_file = Path(__file__).parent.parent / "data" / "canonical_events.csv"
    if not mappings_file:
        mappings_file = Path(__file__).parent.parent / "data" / "venue_mappings.csv"
    
    return EventRegistry(events_file=events_file, mappings_file=mappings_file)


def cmd_stats(args: argparse.Namespace) -> None:
    """Show mapping statistics."""
    registry = setup_registry(args.events_file, args.mappings_file)
    stats = registry.get_coverage_stats()
    
    print("=== Event Registry Statistics ===")
    print(f"Total canonical events: {stats['total_events']}")
    print(f"Total venue mappings: {stats['total_mappings']}")
    print(f"Events with cross-venue mappings: {stats['events_with_cross_venue']}")
    
    print("\n=== Coverage by Venue ===")
    for venue, count in stats['coverage_by_venue'].items():
        print(f"  {venue}: {count} markets")
    
    print("\n=== Coverage by Method ===")
    for method, count in stats['coverage_by_method'].items():
        print(f"  {method}: {count} mappings")


def cmd_list_events(args: argparse.Namespace) -> None:
    """List all canonical events."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    print("=== Canonical Events ===")
    for event_id, event in sorted(registry.events.items()):
        print(f"\n{event_id}")
        print(f"  Type: {event.event_type.value}")
        print(f"  Scope: {event.scope.value}")
        print(f"  Close: {event.date_close}")
        print(f"  Title: {event.display_title}")
        if event.aliases:
            print(f"  Aliases: {', '.join(event.aliases)}")


def cmd_list_mappings(args: argparse.Namespace) -> None:
    """List venue mappings."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    # Filter by venue if specified
    mappings = registry.mappings.values()
    if args.venue:
        mappings = [m for m in mappings if m.venue == args.venue]
    
    print("=== Venue Mappings ===")
    for mapping in sorted(mappings, key=lambda m: m.event_id):
        print(f"\n{mapping.venue}:{mapping.market_id} -> {mapping.event_id}")
        print(f"  Title: {mapping.title_raw}")
        print(f"  Method: {mapping.mapping_method} (confidence: {mapping.confidence})")


def cmd_add_event(args: argparse.Namespace) -> None:
    """Add a new canonical event."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    # Build event ID
    event_id = CanonicalEvent.build_event_id(
        args.event_type,
        args.scope,
        *args.components,
    )
    
    # Check if exists
    if registry.get_event(event_id):
        print(f"Error: Event {event_id} already exists")
        sys.exit(1)
    
    # Parse close date
    try:
        close_date = datetime.fromisoformat(args.close_date)
    except ValueError:
        print(f"Error: Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)
    
    # Create event
    event = CanonicalEvent(
        event_id=event_id,
        event_type=EventType(args.event_type.upper()),
        scope=EventScope(args.scope.upper()),
        date_open=None,
        date_close=close_date,
        canonical_units=args.units or "YES/NO",
        display_title=args.title or event_id,
        resolution_source=args.source or "",
    )
    
    registry.add_event(event)
    registry.save()
    
    print(f"✓ Created event: {event_id}")


def cmd_add_override(args: argparse.Namespace) -> None:
    """Add a manual override mapping."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    # Check if event exists
    event = registry.get_event(args.event_id)
    if not event:
        print(f"Error: Event {args.event_id} not found")
        print("Create the event first with: manage-mappings add-event")
        sys.exit(1)
    
    # Create mapping
    mapping = VenueMapping(
        venue=args.venue,
        market_id=args.market_id,
        event_id=args.event_id,
        title_raw=args.title or "",
        description_raw=args.description or "",
        outcomes=["YES", "NO"],
        confidence=1.0,
        mapping_method="manual_override",
    )
    
    registry.add_mapping(mapping)
    registry.save()
    
    print(f"✓ Created override: {args.venue}:{args.market_id} -> {args.event_id}")


def cmd_test_mapper(args: argparse.Namespace) -> None:
    """Test mapping a market title."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    # Create mapper
    if args.venue == "polymarket":
        mapper = PolymarketMapper(registry)
    elif args.venue == "kalshi":
        mapper = KalshiMapper(registry)
    else:
        print(f"Error: Unknown venue {args.venue}")
        sys.exit(1)
    
    # Test mapping
    event_id = mapper.map_to_event_id(
        market_id=args.market_id or "test_id",
        title=args.title,
        description=args.description or "",
        metadata={},
    )
    
    if event_id:
        print(f"✓ Mapped to: {event_id}")
        
        # Show event details if it exists
        event = registry.get_event(event_id)
        if event:
            print(f"\nEvent Details:")
            print(f"  Type: {event.event_type.value}")
            print(f"  Scope: {event.scope.value}")
            print(f"  Close: {event.date_close}")
    else:
        print("✗ Could not map (abstained)")


def cmd_export(args: argparse.Namespace) -> None:
    """Export mappings to CSV."""
    registry = setup_registry(args.events_file, args.mappings_file)
    
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    registry.save()
    
    print(f"✓ Exported mappings to {output_file}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage event mappings and overrides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Global options
    parser.add_argument(
        "--events-file",
        help="Path to canonical events CSV",
        default=None,
    )
    parser.add_argument(
        "--mappings-file",
        help="Path to venue mappings CSV",
        default=None,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Stats command
    subparsers.add_parser("stats", help="Show mapping statistics")
    
    # List events command
    subparsers.add_parser("list-events", help="List all canonical events")
    
    # List mappings command
    list_mappings = subparsers.add_parser("list-mappings", help="List venue mappings")
    list_mappings.add_argument("--venue", help="Filter by venue")
    
    # Add event command
    add_event = subparsers.add_parser("add-event", help="Add a new canonical event")
    add_event.add_argument("event_type", help="Event type (ELECTION, CRYPTO, etc.)")
    add_event.add_argument("scope", help="Scope (US, GLOBAL, etc.)")
    add_event.add_argument("components", nargs="+", help="Event ID components")
    add_event.add_argument("--close-date", required=True, help="Close date (YYYY-MM-DD)")
    add_event.add_argument("--title", help="Display title")
    add_event.add_argument("--units", help="Canonical units")
    add_event.add_argument("--source", help="Resolution source")
    
    # Add override command
    add_override = subparsers.add_parser("add-override", help="Add manual override mapping")
    add_override.add_argument("venue", help="Venue (polymarket, kalshi)")
    add_override.add_argument("market_id", help="Venue market ID")
    add_override.add_argument("event_id", help="Canonical event ID")
    add_override.add_argument("--title", help="Market title")
    add_override.add_argument("--description", help="Market description")
    
    # Test mapper command
    test_mapper = subparsers.add_parser("test-mapper", help="Test mapping a market title")
    test_mapper.add_argument("venue", help="Venue (polymarket, kalshi)")
    test_mapper.add_argument("title", help="Market title to test")
    test_mapper.add_argument("--market-id", help="Market ID")
    test_mapper.add_argument("--description", help="Market description")
    
    # Export command
    export_cmd = subparsers.add_parser("export", help="Export mappings to CSV")
    export_cmd.add_argument("output", help="Output file path")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to command
    if args.command == "stats":
        cmd_stats(args)
    elif args.command == "list-events":
        cmd_list_events(args)
    elif args.command == "list-mappings":
        cmd_list_mappings(args)
    elif args.command == "add-event":
        cmd_add_event(args)
    elif args.command == "add-override":
        cmd_add_override(args)
    elif args.command == "test-mapper":
        cmd_test_mapper(args)
    elif args.command == "export":
        cmd_export(args)


if __name__ == "__main__":
    main()

