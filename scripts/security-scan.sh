#!/usr/bin/env bash
# Security scanning script for Docker images
# Runs Trivy, Grype, and generates SBOM

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="${1:-scry-ingestor:latest}"
SCAN_DIR="./security-reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}=== Scry_Ingestor Security Scanning ===${NC}"
echo "Image: ${IMAGE_NAME}"
echo "Timestamp: ${TIMESTAMP}"
echo ""

# Create reports directory
mkdir -p "${SCAN_DIR}"

# ============================================================================
# 1. Build the image
# ============================================================================
echo -e "${YELLOW}[1/5] Building Docker image...${NC}"
docker build -t "${IMAGE_NAME}" .
echo -e "${GREEN}✓ Build complete${NC}\n"

# ============================================================================
# 2. Trivy vulnerability scan
# ============================================================================
echo -e "${YELLOW}[2/5] Running Trivy vulnerability scan...${NC}"

if command -v trivy &> /dev/null; then
    # Full vulnerability scan
    trivy image \
        --severity CRITICAL,HIGH,MEDIUM \
        --format json \
        --output "${SCAN_DIR}/trivy-report-${TIMESTAMP}.json" \
        "${IMAGE_NAME}"
    
    # Table format for console
    trivy image \
        --severity CRITICAL,HIGH \
        --format table \
        "${IMAGE_NAME}"
    
    echo -e "${GREEN}✓ Trivy scan complete${NC}"
    echo "   Report: ${SCAN_DIR}/trivy-report-${TIMESTAMP}.json"
else
    echo -e "${RED}✗ Trivy not installed. Skipping...${NC}"
    echo "   Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"
fi

echo ""

# ============================================================================
# 3. Grype vulnerability scan
# ============================================================================
echo -e "${YELLOW}[3/5] Running Grype vulnerability scan...${NC}"

if command -v grype &> /dev/null; then
    grype "${IMAGE_NAME}" \
        --output json \
        --file "${SCAN_DIR}/grype-report-${TIMESTAMP}.json" \
        || true  # Don't fail on vulnerabilities found
    
    # Human-readable output
    grype "${IMAGE_NAME}" --output table || true
    
    echo -e "${GREEN}✓ Grype scan complete${NC}"
    echo "   Report: ${SCAN_DIR}/grype-report-${TIMESTAMP}.json"
else
    echo -e "${RED}✗ Grype not installed. Skipping...${NC}"
    echo "   Install: https://github.com/anchore/grype#installation"
fi

echo ""

# ============================================================================
# 4. Generate SBOM with Syft
# ============================================================================
echo -e "${YELLOW}[4/5] Generating Software Bill of Materials (SBOM)...${NC}"

if command -v syft &> /dev/null; then
    # Generate SBOM in multiple formats
    
    # CycloneDX JSON format
    syft "${IMAGE_NAME}" \
        --output cyclonedx-json \
        --file "${SCAN_DIR}/sbom-cyclonedx-${TIMESTAMP}.json"
    
    # SPDX JSON format
    syft "${IMAGE_NAME}" \
        --output spdx-json \
        --file "${SCAN_DIR}/sbom-spdx-${TIMESTAMP}.json"
    
    # Human-readable table
    syft "${IMAGE_NAME}" --output table
    
    echo -e "${GREEN}✓ SBOM generation complete${NC}"
    echo "   CycloneDX: ${SCAN_DIR}/sbom-cyclonedx-${TIMESTAMP}.json"
    echo "   SPDX: ${SCAN_DIR}/sbom-spdx-${TIMESTAMP}.json"
else
    echo -e "${RED}✗ Syft not installed. Skipping...${NC}"
    echo "   Install: https://github.com/anchore/syft#installation"
fi

echo ""

# ============================================================================
# 5. Docker Scout (if available)
# ============================================================================
echo -e "${YELLOW}[5/5] Running Docker Scout analysis...${NC}"

if docker scout version &> /dev/null 2>&1; then
    docker scout cves "${IMAGE_NAME}" \
        --format sarif \
        --output "${SCAN_DIR}/scout-report-${TIMESTAMP}.sarif" \
        || true
    
    docker scout cves "${IMAGE_NAME}" || true
    
    echo -e "${GREEN}✓ Docker Scout analysis complete${NC}"
    echo "   Report: ${SCAN_DIR}/scout-report-${TIMESTAMP}.sarif"
else
    echo -e "${YELLOW}! Docker Scout not available. Skipping...${NC}"
    echo "   Install Docker Desktop or enable Docker Scout"
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${GREEN}=== Scan Complete ===${NC}"
echo "All reports saved to: ${SCAN_DIR}/"
echo ""
echo "Next steps:"
echo "  1. Review vulnerability reports"
echo "  2. Update dependencies if needed: poetry update"
echo "  3. Rebuild and rescan"
echo "  4. Check SBOM for supply chain security"
echo ""

# Create latest symlinks for easy access
ln -sf "trivy-report-${TIMESTAMP}.json" "${SCAN_DIR}/trivy-latest.json" 2>/dev/null || true
ln -sf "grype-report-${TIMESTAMP}.json" "${SCAN_DIR}/grype-latest.json" 2>/dev/null || true
ln -sf "sbom-cyclonedx-${TIMESTAMP}.json" "${SCAN_DIR}/sbom-latest.json" 2>/dev/null || true

echo -e "${GREEN}Latest reports linked:${NC}"
echo "  ${SCAN_DIR}/trivy-latest.json"
echo "  ${SCAN_DIR}/grype-latest.json"
echo "  ${SCAN_DIR}/sbom-latest.json"
