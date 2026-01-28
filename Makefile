.PHONY: test run-ui run-cli scan-night scan-humanized validate

test:
	pytest -q

run-ui:
	streamlit run apps/streamlit/app.py

run-cli:
	python3 apps/cli/microdose_bot.py

scan-night:
	python3 scripts/runners/night_scanner.py

scan-humanized:
	python3 scripts/runners/humanized_night_scanner.py

validate:
	./scripts/ops/run_validations.sh
