#!/bin/bash
# Migrate existing features to include phase_reports field
# Run from the AIAgentCoreRules repo root: bash Tools/feature-state/migrate_phase_reports.sh [features-root]

set -e

FEATURES_ROOT="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="python3"

if [[ ! -d "$FEATURES_ROOT" ]]; then
    echo "error: features root '$FEATURES_ROOT' not found"
    exit 1
fi

count=0
migrated=0
already_have=0

echo "Scanning features in: $FEATURES_ROOT"
echo

for state_file in "$FEATURES_ROOT"/*/state.json; do
    dir=$(dirname "$state_file")
    feature=$(basename "$dir")
    count=$((count + 1))

    # Check if phase_reports field exists
    if $PYTHON -c "import json; d=json.load(open('$state_file')); d['phase_reports']" 2>/dev/null; then
        already_have=$((already_have + 1))
        echo "✓ $feature — has phase_reports"
    else
        # Add phase_reports field
        $PYTHON << EOF
import json
from pathlib import Path

state_file = Path('$state_file')
state = json.loads(state_file.read_text())

if 'phase_reports' not in state:
    state['phase_reports'] = {}

    # For any completed phases, add a note that report was added post-phase
    for gate in state.get('gates', []):
        if gate.get('phase_completed'):
            import re
            match = re.match(r'Phase (\d+)', gate['phase_completed'])
            if match:
                phase_num = int(match.group(1))
                phase_names = ['intake', 'discovery', 'design', 'implementation', 'unit_tests', 'integration', 'verification', 'retrospective']
                if phase_num <= len(phase_names):
                    phase_key = f'{phase_num}_{phase_names[phase_num-1]}'
                    # Only add placeholder if the feature doesn't already have a report for this phase
                    if phase_key not in state['phase_reports']:
                        # Don't actually create a file, just note that this phase was completed before the reporting system
                        pass

state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
print(f"  Added phase_reports field")
EOF
        migrated=$((migrated + 1))
        echo "✓ $feature — migrated (added phase_reports)"
    fi
done

echo
echo "Summary:"
echo "  Total features:     $count"
echo "  Already migrated:   $already_have"
echo "  Newly migrated:     $migrated"
