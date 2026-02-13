
# Universal Makefile for Stent Optimization Project

PYTHON = python3
CLI = src/cli.py

.PHONY: help install test check-env run-campaign presentation

help:
	@echo "Available commands:"
	@echo "  make install         - Install dependencies"
	@echo "  make check-env       - Verify environment setup"
	@echo "  make test            - Run all unit tests"
	@echo "  make run-campaign    - Run the optimization loop (default: campaign_001)"
	@echo "  make presentation    - Generate the project presentation"

install:
	pip install -r requirements.txt

check-env:
	$(PYTHON) $(CLI) check-env

test:
	$(PYTHON) $(CLI) test

run-campaign:
	$(PYTHON) $(CLI) run-campaign --campaign campaign_001 --batch_size 5

presentation:
	$(PYTHON) $(CLI) generate-presentation --output admin/stent_pipeline_final.pptx
