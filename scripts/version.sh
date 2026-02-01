#!/usr/bin/env bash
# Semantic versioning helper script
# Follows conventional commits specification for automated versioning

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get current version from git tags
get_current_version() {
    git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0"
}

# Parse semantic version
parse_version() {
    local version=$1
    version=${version#v}  # Remove 'v' prefix
    
    local major minor patch
    IFS='.' read -r major minor patch <<< "$version"
    
    echo "$major $minor $patch"
}

# Determine version bump from commit messages
determine_bump() {
    local base_ref=${1:-$(get_current_version)}
    
    # Get commits since last tag
    local commits=$(git log "${base_ref}..HEAD" --pretty=format:"%s" 2>/dev/null || echo "")
    
    if [ -z "$commits" ]; then
        echo "none"
        return
    fi
    
    # Check for breaking changes (MAJOR bump)
    if echo "$commits" | grep -qE "^[a-z]+(\(.+\))?!:|BREAKING CHANGE:"; then
        echo "major"
        return
    fi
    
    # Check for new features (MINOR bump)
    if echo "$commits" | grep -qE "^feat(\(.+\))?:"; then
        echo "minor"
        return
    fi
    
    # Check for fixes or other changes (PATCH bump)
    if echo "$commits" | grep -qE "^(fix|perf|refactor|docs|style|test|chore)(\(.+\))?:"; then
        echo "patch"
        return
    fi
    
    echo "none"
}

# Calculate next version
calculate_next_version() {
    local current_version=$1
    local bump_type=$2
    
    read -r major minor patch <<< $(parse_version "$current_version")
    
    case "$bump_type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "$current_version"
            return
            ;;
    esac
    
    echo "v${major}.${minor}.${patch}"
}

# Generate changelog from conventional commits
generate_changelog() {
    local base_ref=${1:-$(get_current_version)}
    local head_ref=${2:-HEAD}
    
    echo -e "${BLUE}## Changelog${NC}\n"
    
    # Breaking Changes
    local breaking=$(git log "${base_ref}..${head_ref}" --pretty=format:"%s%n%b" | \
        grep -E "^(BREAKING CHANGE:|[a-z]+(\(.+\))?!:)" || true)
    if [ -n "$breaking" ]; then
        echo -e "${RED}### ⚠️ BREAKING CHANGES${NC}\n"
        echo "$breaking" | sed 's/^/- /'
        echo ""
    fi
    
    # Features
    local features=$(git log "${base_ref}..${head_ref}" --pretty=format:"%s" | \
        grep -E "^feat(\(.+\))?:" || true)
    if [ -n "$features" ]; then
        echo -e "${GREEN}### ✨ Features${NC}\n"
        echo "$features" | sed 's/^feat/- feat/'
        echo ""
    fi
    
    # Bug Fixes
    local fixes=$(git log "${base_ref}..${head_ref}" --pretty=format:"%s" | \
        grep -E "^fix(\(.+\))?:" || true)
    if [ -n "$fixes" ]; then
        echo -e "${GREEN}### 🐛 Bug Fixes${NC}\n"
        echo "$fixes" | sed 's/^fix/- fix/'
        echo ""
    fi
    
    # Performance
    local perf=$(git log "${base_ref}..${head_ref}" --pretty=format:"%s" | \
        grep -E "^perf(\(.+\))?:" || true)
    if [ -n "$perf" ]; then
        echo -e "${YELLOW}### ⚡ Performance${NC}\n"
        echo "$perf" | sed 's/^perf/- perf/'
        echo ""
    fi
    
    # Documentation
    local docs=$(git log "${base_ref}..${head_ref}" --pretty=format:"%s" | \
        grep -E "^docs(\(.+\))?:" || true)
    if [ -n "$docs" ]; then
        echo -e "${BLUE}### 📝 Documentation${NC}\n"
        echo "$docs" | sed 's/^docs/- docs/'
        echo ""
    fi
}

# Main function
main() {
    local command=${1:-suggest}
    
    case "$command" in
        suggest)
            local current=$(get_current_version)
            local bump=$(determine_bump "$current")
            local next=$(calculate_next_version "$current" "$bump")
            
            echo -e "${BLUE}Current version:${NC} $current"
            echo -e "${YELLOW}Suggested bump:${NC} $bump"
            echo -e "${GREEN}Next version:${NC} $next"
            
            if [ "$bump" == "none" ]; then
                echo -e "\n${YELLOW}No version bump needed (no conventional commits found)${NC}"
            fi
            ;;
        
        bump)
            local bump_type=${2:-auto}
            local current=$(get_current_version)
            
            if [ "$bump_type" == "auto" ]; then
                bump_type=$(determine_bump "$current")
            fi
            
            if [ "$bump_type" == "none" ]; then
                echo -e "${YELLOW}No version bump needed${NC}"
                exit 0
            fi
            
            local next=$(calculate_next_version "$current" "$bump_type")
            
            echo -e "${GREEN}Bumping version from $current to $next${NC}"
            
            # Update pyproject.toml
            sed -i "s/^version = .*/version = \"${next#v}\"/" pyproject.toml
            
            # Create git tag
            git tag -a "$next" -m "Release $next"
            
            echo -e "${GREEN}✓ Version bumped to $next${NC}"
            echo -e "  Run ${BLUE}git push --tags${NC} to publish"
            ;;
        
        changelog)
            generate_changelog "${2:-$(get_current_version)}" "${3:-HEAD}"
            ;;
        
        *)
            echo "Usage: $0 {suggest|bump [major|minor|patch|auto]|changelog [base] [head]}"
            echo ""
            echo "Commands:"
            echo "  suggest     - Suggest next version based on commits"
            echo "  bump        - Bump version and create tag"
            echo "  changelog   - Generate changelog from commits"
            exit 1
            ;;
    esac
}

main "$@"
