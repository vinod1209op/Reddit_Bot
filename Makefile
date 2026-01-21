.PHONY: test run-ui run-cli scan-night scan-humanized

test:
\tpython3 -m unittest discover -v -s tests

run-ui:
\tstreamlit run apps/streamlit/app.py

run-cli:
\tpython3 apps/cli/microdose_bot.py

scan-night:
\tpython3 scripts/runners/night_scanner.py

scan-humanized:
\tpython3 scripts/runners/humanized_night_scanner.py
