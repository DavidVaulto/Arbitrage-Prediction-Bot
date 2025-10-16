#!/bin/bash
# Quick status check for discovery session

cd "$(dirname "$0")"

echo "======================================================================"
echo "🔍 DISCOVERY SESSION STATUS CHECK"
echo "======================================================================"
echo ""

# Check if processes are running
if [ -f discovery.pid ]; then
    PID=$(cat discovery.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ Discovery Process: RUNNING (PID $PID)"
    else
        echo "❌ Discovery Process: STOPPED (PID $PID not found)"
    fi
else
    echo "⚠️  No discovery.pid file found"
fi

echo ""

# Check data file
DATA_FILE="data/discovery_20251016_130024.parquet"
if [ -f "$DATA_FILE" ]; then
    echo "📊 Data File: $DATA_FILE"
    ls -lh "$DATA_FILE"
    echo ""
    
    # Show quick stats
    python3 << 'EOF'
import pandas as pd
from datetime import datetime

df = pd.read_parquet('data/discovery_20251016_130024.parquet')
elapsed = (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60
progress = (elapsed / 30) * 100

print(f"   Rows: {len(df):,}")
print(f"   Elapsed: {elapsed:.1f} / 30.0 minutes ({progress:.1f}%)")
print(f"   Venues: {', '.join(df['venue'].unique())}")
print(f"   Markets: {df.groupby('venue')['contract_id'].nunique().to_dict()}")
EOF
else
    echo "⏳ Data file not created yet"
fi

echo ""
echo "======================================================================"
echo "📋 Quick Commands:"
echo "   View progress:    tail -f monitor.log"
echo "   View data:        python3 -c \"import pandas as pd; print(pd.read_parquet('$DATA_FILE').tail())\""
echo "   Stop discovery:   kill \$(cat discovery.pid)"
echo "======================================================================"

