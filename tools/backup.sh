#!/usr/bin/env bash
set -euo pipefail

# Resolve the directory this script lives in (your project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Name of the project folder (e.g. "podsite")
PROJECT_NAME="$(basename "$SCRIPT_DIR")"

# Where to put backups (one level up from project root)
BACKUP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Timestamp for uniqueness
STAMP="$(date +%Y%m%d_%H%M%S)"

# Backup directory name, e.g. "podsite-backup-20251203_142755"
BACKUP_DIR="${BACKUP_ROOT}/${PROJECT_NAME}-backup-${STAMP}"

echo "Creating backup of '$PROJECT_NAME'..."
echo "Source: $SCRIPT_DIR"
echo "Dest:   $BACKUP_DIR"

# Copy the entire project directory
cp -R "$SCRIPT_DIR" "$BACKUP_DIR"

echo "Backup complete."

