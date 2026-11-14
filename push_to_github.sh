#!/usr/bin/env bash
# HimShiksha API - Push Updates to GitHub
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "      HIMSHIKSHA API - GITHUB ONE-CLICK UPDATE TOOL"
echo "========================================================"
echo "Working Directory: $PWD"
echo ""

echo "[1/4] Checking Git Status..."
git status
echo ""

read -p "Do you want to stage, commit, and push these changes to GitHub? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "[INFO] Update cancelled by user."
    exit 0
fi

read -p "Enter commit message (Press ENTER for default): " USER_MSG
COMMIT_MSG="${USER_MSG:-Update HimShiksha API routes and services ($(date '+%Y-%m-%d %H:%M:%S'))}"

echo ""
echo "[2/4] Staging modified and new API files..."
git add main.py requirements.txt routes/ services/ utils/ schemas/ Procfile render.yaml .gitignore
git status --short

echo ""
echo "[3/4] Committing changes..."
git commit -m "$COMMIT_MSG" || echo "[NOTE] No new changes to commit."

echo ""
echo "[4/4] Pushing to GitHub (origin main)..."
git push origin main

echo ""
echo "========================================================"
echo "  SUCCESS: Changes pushed to GitHub (origin main)!"
echo "  Render will automatically build and deploy the update."
echo "========================================================"
