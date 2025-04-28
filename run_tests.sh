#!/bin/bash
# Run all tests with coverage

# Set colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "\n${BLUE}Running integration tests...${NC}"
python -m pytest test/test_integration.py -v --integration

echo -e "\n${BLUE}Running full pipeline test...${NC}"
python -m pytest test/test_integration.py::test_full_pipeline -v --integration --runslow

echo -e "\n${BLUE}Generating coverage report...${NC}"
python -m pytest test_pipeline.py test/test_integration.py -v --integration --runslow --cov=. --cov-report=html

echo -e "\n${GREEN}All tests completed! Coverage report available in 'htmlcov/' directory${NC}"
echo -e "Open htmlcov/index.html in your browser to view detailed coverage information" 
