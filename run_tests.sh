#!/bin/bash
# Script to run tests for Hai Agent

# Set up colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running tests for Hai Agent...${NC}"
echo

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest is not installed.${NC}"
    echo -e "Installing required dependencies..."
    pip install -r requirements.txt
fi

# Parse command line arguments
COVERAGE=false
VERBOSE=false
SPECIFIC_TEST=""

for arg in "$@"; do
    case $arg in
        --no-cov)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            SPECIFIC_TEST=$arg
            shift
            ;;
    esac
done

# Build the pytest command
PYTEST_CMD="pytest"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
fi

# Add coverage options if coverage is enabled
if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=src --cov-report=term --cov-report=html"
fi

if [ ! -z "$SPECIFIC_TEST" ]; then
    PYTEST_CMD="$PYTEST_CMD $SPECIFIC_TEST"
fi

# Run the tests
echo -e "${GREEN}Executing: $PYTEST_CMD${NC}"
echo
eval $PYTEST_CMD

# Check if tests were successful
if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}All tests passed!${NC}"
    
    if [ "$COVERAGE" = true ]; then
        echo -e "${YELLOW}Coverage report generated in htmlcov/ directory${NC}"
        echo -e "Open htmlcov/index.html in your browser to view the detailed report"
    fi
else
    echo
    echo -e "${RED}Some tests failed. Please check the output above for details.${NC}"
fi
